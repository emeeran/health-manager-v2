"""docs/modification-idea.md features: auto-generated chat titles and the
local auto-backup schedule (default-on + Settings endpoints).

AI callables are patched at module scope (same pattern as
test_modifications.py); conftest points Ollama at a closed port so an
unpatched call can never reach a real provider.
"""

import json

import pytest_asyncio
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Household
from tests.test_search_dashboard import _create_member


class _FakeChatProvider:
    def __init__(self) -> None:
        self.name = "fake"
        self.model = "fake-model"
        self.local = True
        self.timeout = 5

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs) -> str:
        return "Answer from the records: keep taking the morning dose."


@pytest_asyncio.fixture
def fake_chat_provider(monkeypatch):
    from app.services.ai import router as ai_router

    provider = _FakeChatProvider()

    async def fake_plan(db, household_id, local_only: bool = False):
        return [provider]

    async def fake_available(plan):
        return [provider]

    monkeypatch.setattr(ai_router, "plan_for_household", fake_plan)
    monkeypatch.setattr(ai_router, "available_providers", fake_available)
    return provider


async def _household_settings() -> dict:
    async with SessionLocal() as db:
        household = (
            await db.scalars(select(Household).order_by(Household.created_at).limit(1))
        ).first()
        assert household is not None
        return json.loads(household.settings_json) if household.settings_json else {}


# ── auto-generated chat titles ────────────────────────────────────────────


async def test_derive_title_first_line_collapsed():
    from app.services.chat_service import derive_title

    assert derive_title("What do my latest\nlab reports mean?") == "What do my latest"
    assert derive_title("  why   am I dizzy ?") == "why am I dizzy ?"


async def test_derive_title_clamps_with_ellipsis():
    from app.services.chat_service import derive_title

    title = derive_title("ab" * 100)
    assert title.endswith("…")
    assert len(title) <= 60


async def test_chat_conversation_auto_titles_from_first_message(
    auth_client, fake_chat_provider
):
    member = await _create_member(auth_client, "Asha")
    resp = await auth_client.post(
        "/api/v1/conversations", json={"member_id": member["id"]}
    )
    assert resp.status_code == 201, resp.text
    conversation = resp.json()
    assert conversation["title"] is None

    resp = await auth_client.post(
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "What do my latest\nlab reports mean?"},
    )
    assert resp.status_code == 200, resp.text

    listing = await auth_client.get("/api/v1/conversations")
    assert listing.status_code == 200, listing.text
    titles = {c["id"]: c["title"] for c in listing.json()}
    assert titles[conversation["id"]] == "What do my latest"


async def test_chat_explicit_title_is_never_overwritten(
    auth_client, fake_chat_provider
):
    resp = await auth_client.post(
        "/api/v1/conversations", json={"title": "Surgery questions"}
    )
    assert resp.status_code == 201, resp.text
    conversation = resp.json()

    resp = await auth_client.post(
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "Is anaesthesia safe for me?"},
    )
    assert resp.status_code == 200, resp.text

    listing = await auth_client.get("/api/v1/conversations")
    titles = {c["id"]: c["title"] for c in listing.json()}
    assert titles[conversation["id"]] == "Surgery questions"


# ── local auto-backup schedule ────────────────────────────────────────────


async def test_backup_schedule_defaults_to_daily(auth_client):
    resp = await auth_client.get("/api/v1/backup/schedule")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"schedule": "daily"}


async def test_backup_schedule_roundtrip(auth_client):
    resp = await auth_client.put(
        "/api/v1/backup/schedule", json={"schedule": "weekly"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"schedule": "weekly"}

    resp = await auth_client.get("/api/v1/backup/schedule")
    assert resp.json() == {"schedule": "weekly"}


async def test_backup_schedule_rejects_unknown_values(auth_client):
    resp = await auth_client.put("/api/v1/backup/schedule", json={"schedule": "hourly"})
    assert resp.status_code == 422


async def test_ai_config_put_preserves_backup_schedule(auth_client):
    resp = await auth_client.put("/api/v1/backup/schedule", json={"schedule": "weekly"})
    assert resp.status_code == 200, resp.text

    resp = await auth_client.put(
        "/api/v1/household/ai-config",
        json={"primary_provider": "auto", "providers": []},
    )
    assert resp.status_code == 200, resp.text

    settings = await _household_settings()
    assert settings["backup_schedule"] == "weekly"
    assert settings["primary_provider"] == "auto"
