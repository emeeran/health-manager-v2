"""Phase 8: in-app notifications — visibility, unread counts, mark-read."""

import uuid

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Notification
from app.services import notifications as svc
from tests.test_household_admin import _invite_and_accept


async def _household_id(client) -> uuid.UUID:
    resp = await client.get("/api/v1/household")
    return uuid.UUID(resp.json()["id"])


@pytest.mark.asyncio
async def test_create_list_unread_readall(auth_client, session_factory):
    hid = await _household_id(auth_client)
    async with session_factory() as session:
        svc.create_notification(
            session, household_id=hid, title="Refill soon", body="Metformin in 5 days"
        )
        svc.create_notification(session, household_id=hid, title="Backup done")
        await session.commit()

    listed = (await auth_client.get("/api/v1/notifications")).json()
    assert listed["unread"] == 2
    titles = {item["title"] for item in listed["items"]}
    assert titles == {"Refill soon", "Backup done"}
    refill = next(i for i in listed["items"] if i["title"] == "Refill soon")
    assert refill["body"] == "Metformin in 5 days"  # decrypted at read
    assert refill["read"] is False

    marked = await auth_client.post("/api/v1/notifications/read-all")
    assert marked.status_code == 200

    after = (await auth_client.get("/api/v1/notifications/unread-count")).json()
    assert after["unread"] == 0
    async with session_factory() as session:
        rows = (await session.scalars(select(Notification.read_at))).all()
    assert all(r is not None for r in rows)


@pytest.mark.asyncio
async def test_targeted_notification_invisible_to_others(auth_client):
    member_client = await _invite_and_accept(auth_client, "member", "peer")
    hid = await _household_id(auth_client)

    users = (await auth_client.get("/api/v1/household/users")).json()
    peer_id = uuid.UUID(next(u["user_id"] for u in users if u["username"] == "peer"))

    async with SessionLocal() as session:
        svc.create_notification(session, household_id=hid, title="For peer only", user_id=peer_id)
        svc.create_notification(session, household_id=hid, title="For everyone")
        await session.commit()

    admin_view = (await auth_client.get("/api/v1/notifications")).json()
    admin_titles = {i["title"] for i in admin_view["items"]}
    assert "For peer only" not in admin_titles
    assert "For everyone" in admin_titles

    peer_view = (await member_client.get("/api/v1/notifications")).json()
    peer_titles = {i["title"] for i in peer_view["items"]}
    assert peer_titles == {"For peer only", "For everyone"}
    assert peer_view["unread"] == 2


@pytest.mark.asyncio
async def test_mark_single_read_scoped(auth_client):
    hid = await _household_id(auth_client)
    async with SessionLocal() as session:
        row = svc.create_notification(session, household_id=hid, title="One")
        await session.commit()
        nid = row.id

    read = await auth_client.post(f"/api/v1/notifications/{nid}/read")
    assert read.status_code == 200
    after = (await auth_client.get("/api/v1/notifications/unread-count")).json()
    assert after["unread"] == 0

    missing = await auth_client.post(f"/api/v1/notifications/{uuid.uuid4()}/read")
    assert missing.status_code == 404
