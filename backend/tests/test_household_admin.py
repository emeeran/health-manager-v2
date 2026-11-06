"""Phase 8: household admin — roles, invitations, audit, AI config.

Role-matrix discipline: the owner (registered user) is admin; invited users
carry their invitation's role; viewers are read-only via middleware.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models import HouseholdInvitation

# ── helpers ───────────────────────────────────────────────────────────


def _extra_client() -> httpx.AsyncClient:
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _invite_and_accept(
    client, role: str, username: str, password: str = "TestPass1!"
) -> httpx.AsyncClient:
    """Admin creates an invitation; a fresh client accepts it."""
    created = await client.post("/api/v1/household/users/invitations", json={"role": role})
    assert created.status_code == 201, created.text
    token = created.json()["token"]

    new_client = _extra_client()
    accepted = await new_client.post(
        "/api/v1/household/users/invitations/accept",
        json={"token": token, "username": username, "password": password},
    )
    assert accepted.status_code == 200, accepted.text
    return new_client


# ── membership & roles ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_is_admin_and_listed(auth_client):
    info = await auth_client.get("/api/v1/household")
    assert info.status_code == 200
    assert info.json()["my_role"] == "admin"

    users = await auth_client.get("/api/v1/household/users")
    assert users.status_code == 200
    rows = users.json()
    assert len(rows) == 1
    assert rows[0]["is_primary"] is True
    assert rows[0]["role"] == "admin"


@pytest.mark.asyncio
async def test_role_matrix(auth_client):
    viewer_client = await _invite_and_accept(auth_client, "viewer", "viewy")

    # Reads pass for viewers…
    assert (await viewer_client.get("/api/v1/members")).status_code == 200
    assert (await viewer_client.get("/api/v1/medications")).status_code in (200, 404)

    # …and non-allowlisted reads of admin surfaces fail on the role guard.
    assert (await viewer_client.get("/api/v1/household/users")).status_code == 403
    assert (await viewer_client.get("/api/v1/security-audit")).status_code == 403

    # Mutations are blocked by the middleware with the viewer message…
    blocked = await viewer_client.post("/api/v1/members", json={"name": "X"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Viewer role is read-only"
    assert (
        await viewer_client.patch("/api/v1/members/00000000-0000-0000-0000-000000000000")
    ).status_code == 403

    # …but allowlisted read-only POST prefixes and self-scoped notifications
    # stay open.
    assert (await viewer_client.post("/api/v1/notifications/read-all")).status_code == 200

    # Unauthenticated mutations 401 (auth fires before the role gate).
    async with _extra_client() as anon:
        anon_blocked = await anon.post("/api/v1/members", json={"name": "X"})
    assert anon_blocked.status_code == 401


@pytest.mark.asyncio
async def test_role_change_and_audit(auth_client):
    member_client = await _invite_and_accept(auth_client, "member", "membry")

    users = (await auth_client.get("/api/v1/household/users")).json()
    target = next(u for u in users if u["username"] == "membry")

    demoted = await auth_client.patch(
        f"/api/v1/household/users/{target['user_id']}", json={"role": "viewer"}
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "viewer"

    # Demotion takes effect immediately (middleware sees the new role).
    blocked = await member_client.post("/api/v1/members", json={"name": "X"})
    assert blocked.status_code == 403

    audit = (await auth_client.get("/api/v1/security-audit")).json()
    actions = [entry["action"] for entry in audit]
    assert "household.role_change" in actions
    role_entry = next(e for e in audit if e["action"] == "household.role_change")
    assert "membry" in role_entry["detail"]


@pytest.mark.asyncio
async def test_owner_cannot_be_demoted_or_removed(auth_client):
    users = (await auth_client.get("/api/v1/household/users")).json()
    owner_id = users[0]["user_id"]

    demote = await auth_client.patch(f"/api/v1/household/users/{owner_id}", json={"role": "viewer"})
    assert demote.status_code == 400

    remove = await auth_client.delete(f"/api/v1/household/users/{owner_id}")
    assert remove.status_code == 400


@pytest.mark.asyncio
async def test_remove_user_deactivates(auth_client):
    member_client = await _invite_and_accept(auth_client, "member", "goner")
    users = (await auth_client.get("/api/v1/household/users")).json()
    target = next(u for u in users if u["username"] == "goner")

    assert (
        await auth_client.delete(f"/api/v1/household/users/{target['user_id']}")
    ).status_code == 204

    # The removed user can no longer act (account deactivated).
    assert (await member_client.get("/api/v1/members")).status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoints_require_admin(auth_client):
    member_client = await _invite_and_accept(auth_client, "member", "plain")
    assert (await member_client.get("/api/v1/household/users")).status_code == 403
    assert (
        await member_client.post("/api/v1/household/users/invitations", json={})
    ).status_code == 403
    renamed = await member_client.patch("/api/v1/household", json={"name": "Nope"})
    assert renamed.status_code == 403


# ── invitations ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invitation_single_use_and_listing(auth_client):
    created = await auth_client.post("/api/v1/household/users/invitations", json={"role": "member"})
    assert created.status_code == 201
    body = created.json()
    assert len(body["token"]) >= 16

    listed = (await auth_client.get("/api/v1/household/users/invitations")).json()
    assert len(listed) == 1
    assert "token" not in listed[0]  # raw token shown once, never listed
    assert listed[0]["accepted"] is False

    # Accept it…
    async with _extra_client() as joiner:
        accepted = await joiner.post(
            "/api/v1/household/users/invitations/accept",
            json={
                "token": body["token"],
                "username": "second",
                "password": "TestPass1!",
            },
        )
    assert accepted.status_code == 200

    listed = (await auth_client.get("/api/v1/household/users/invitations")).json()
    assert listed[0]["accepted"] is True

    # …and the replay is rejected.
    async with _extra_client() as replay:
        replayed = await replay.post(
            "/api/v1/household/users/invitations/accept",
            json={
                "token": body["token"],
                "username": "third",
                "password": "TestPass1!",
            },
        )
    assert replayed.status_code == 400


@pytest.mark.asyncio
async def test_expired_invitation_rejected(auth_client, session_factory):
    created = await auth_client.post("/api/v1/household/users/invitations", json={"role": "member"})
    token = created.json()["token"]

    async with session_factory() as session:
        row = await session.scalar(select(HouseholdInvitation))
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

    async with _extra_client() as new_client:
        rejected = await new_client.post(
            "/api/v1/household/users/invitations/accept",
            json={"token": token, "username": "late", "password": "TestPass1!"},
        )
    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_invite_works_when_registration_closed(auth_client, monkeypatch):
    from app.core.config import get_settings

    frozen = get_settings().model_copy(update={"ALLOW_REGISTRATION": False})
    monkeypatch.setattr("app.core.config.get_settings", lambda: frozen)

    assert (
        await auth_client.post(
            "/api/v1/auth/register",
            json={"username": "walkin", "password": "TestPass1!"},
        )
    ).status_code == 403  # open registration closed…

    await _invite_and_accept(auth_client, "member", "invited")  # …invites still work


@pytest.mark.asyncio
async def test_accept_conflicting_username_409(auth_client):
    created = await auth_client.post("/api/v1/household/users/invitations", json={"role": "member"})
    token = created.json()["token"]
    async with _extra_client() as new_client:
        conflict = await new_client.post(
            "/api/v1/household/users/invitations/accept",
            json={
                "token": token,
                "username": "testuser",  # the admin's existing username
                "password": "TestPass1!",
            },
        )
    assert conflict.status_code == 409


# ── household rename + AI config ──────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_and_ai_config_roundtrip(auth_client):
    renamed = await auth_client.patch("/api/v1/household", json={"name": "House of Test"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "House of Test"

    defaults = (await auth_client.get("/api/v1/household/ai-config")).json()
    assert defaults["primary_provider"] == "auto"
    assert defaults["providers"] == []

    config = {
        "primary_provider": "local",
        "providers": [
            {"name": "openai", "enabled": False},
            {"name": "ollama", "model": "llama3:8b"},
        ],
    }
    put = await auth_client.put("/api/v1/household/ai-config", json=config)
    assert put.status_code == 200
    got = (await auth_client.get("/api/v1/household/ai-config")).json()
    assert got["primary_provider"] == "local"
    assert got["providers"] == [
        {"name": "openai", "enabled": False, "model": None, "base_url": None},
        {"name": "ollama", "enabled": True, "model": "llama3:8b", "base_url": None},
    ]

    audit = (await auth_client.get("/api/v1/security-audit")).json()
    assert "household.ai_config" in [e["action"] for e in audit]


@pytest.mark.asyncio
async def test_ai_config_rejects_metadata_urls(auth_client):
    blocked = await auth_client.put(
        "/api/v1/household/ai-config",
        json={
            "primary_provider": "cloud",
            "providers": [{"name": "ollama", "base_url": "http://169.254.169.254:11434"}],
        },
    )
    assert blocked.status_code == 422


# ── plan integration ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_for_household_honors_config(auth_client, session_factory, monkeypatch):
    from app.models import Household
    from app.services.ai import router as ai_router

    # Two cloud specs + ollama regardless of the test env's (empty) keys.
    monkeypatch.setattr(
        ai_router,
        "_cloud_specs",
        lambda: [
            ("openai", "key", "https://api.openai.com/v1", "gpt-4o-mini"),
            ("groq", "key", "https://api.groq.com/openai/v1", "llama-3.3-70b"),
        ],
    )

    await auth_client.put(
        "/api/v1/household/ai-config",
        json={
            "primary_provider": "auto",
            "providers": [{"name": "openai", "enabled": False}],
        },
    )

    async with session_factory() as session:
        household_id = (await session.scalars(select(Household.id))).first()

        plan = await ai_router.plan_for_household(session, household_id)
        assert [p.name for p in plan] == ["groq", "ollama"]  # openai disabled

        local_plan = await ai_router.plan_for_household(session, household_id, local_only=True)
        assert [p.name for p in local_plan] == ["ollama"]

        # primary_provider=local forces local-only without the flag.
        await auth_client.put("/api/v1/household/ai-config", json={"primary_provider": "local"})
        forced = await ai_router.plan_for_household(session, household_id)
        assert [p.name for p in forced] == ["ollama"]
