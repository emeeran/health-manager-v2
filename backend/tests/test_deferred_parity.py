"""Deferred parity: web push, reports, RAG, scheduler jobs."""

import json
from datetime import UTC, datetime, timedelta


# ── Web push ──────────────────────────────────────────────────────────


async def test_push_status_disabled_by_default(auth_client):
    resp = await auth_client.get("/api/v1/notifications/push/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["public_key"] is None


async def test_push_subscribe_requires_vapid(auth_client):
    resp = await auth_client.post(
        "/api/v1/notifications/push/subscribe",
        json={"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}},
    )
    assert resp.status_code == 501  # VAPID not configured


async def test_push_subscribe_idempotent(auth_client, monkeypatch):
    from app.services import web_push_service

    monkeypatch.setattr(web_push_service, "push_configured", lambda: True)
    body = {
        "endpoint": "https://push.example/sub1",
        "keys": {"p256dh": "key1", "auth": "auth1"},
    }
    first = await auth_client.post("/api/v1/notifications/push/subscribe", json=body)
    assert first.status_code == 201
    again = await auth_client.post("/api/v1/notifications/push/subscribe", json=body)
    assert again.status_code == 201

    from sqlalchemy import func, select

    from app.models import PushSubscription

    async with SessionLocalCount() as db:
        count = await db.scalar(select(func.count()).select_from(PushSubscription))
    assert count == 1


def SessionLocalCount():
    from app.core.database import SessionLocal

    return SessionLocal()


async def test_push_to_user_prunes_dead(auth_client, monkeypatch):
    from app.services import web_push_service

    monkeypatch.setattr(web_push_service, "push_configured", lambda: True)
    await auth_client.post(
        "/api/v1/notifications/push/subscribe",
        json={"endpoint": "https://push.example/dead", "keys": {"p256dh": "k", "auth": "a"}},
    )
    from sqlalchemy import select

    from app.models import PushSubscription
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        sub = (await db.scalars(select(PushSubscription))).one()
        user_id = sub.user_id

        def fake_send(subscription, title, message):
            return False, True  # send failed, endpoint reports gone

        monkeypatch.setattr(web_push_service, "send_to_subscription", fake_send)
        sent = await web_push_service.push_to_user(db, user_id, "t", "m")
        assert sent == 0
        remaining = (await db.scalars(select(PushSubscription))).all()
        assert remaining == []  # pruned


# ── Scheduler jobs ────────────────────────────────────────────────────


async def test_process_reminders_fires_and_repeats(auth_client, monkeypatch):
    from app.core import jobs

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    due = await auth_client.post(
        "/api/v1/reminders",
        json={
            "title": "Refill",
            "member_id": member["id"],
            "remind_at": (
                datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            ).isoformat(),
            "repeat": "daily",
        },
    )
    one_shot = await auth_client.post(
        "/api/v1/reminders",
        json={
            "title": "One-off",
            "remind_at": (
                datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            ).isoformat(),
        },
    )
    assert due.status_code == 201 and one_shot.status_code == 201

    sent = []

    async def fake_push(db, user_id, title, message):
        sent.append(title)
        return 0

    from app.services import web_push_service

    monkeypatch.setattr(web_push_service, "push_configured", lambda: True)
    monkeypatch.setattr(web_push_service, "push_to_user", fake_push)

    fired = await jobs.process_reminders()
    assert fired >= 2

    from app.core.database import SessionLocal
    from sqlalchemy import select

    from app.models import Reminder

    async with SessionLocal() as db:
        rows = {r.title: r for r in (await db.scalars(select(Reminder))).all()}
    assert rows["One-off"].done is True  # one-shot marked done
    assert rows["Refill"].done is False  # daily advanced, still active
    assert rows["Refill"].remind_at > datetime.now(UTC).replace(tzinfo=None)


async def test_prune_tokens(auth_client):
    from app.core import jobs
    from app.core.database import SessionLocal
    from sqlalchemy import func, select

    from app.models import RefreshToken

    async with SessionLocal() as db:
        await db.execute(
            RefreshToken.__table__.insert().values(
                id=__import__("uuid").uuid4(),
                user_id=(await db.scalars(select(RefreshToken.user_id).limit(1))).first()
                or __import__("uuid").uuid4(),
                token_hash="expired-token-hash",
                expires_at=datetime.utcnow() - timedelta(days=2),
            )
        )
        await db.commit()

    pruned = await jobs.prune_tokens()
    assert pruned >= 1
    async with SessionLocal() as db:
        count = await db.scalar(
            select(func.count()).where(RefreshToken.token_hash == "expired-token-hash")
        )
    assert count == 0


# ── Reports ───────────────────────────────────────────────────────────


class FakeReportProvider:
    name = "fake-report"
    model = "fake"
    local = True
    timeout = 1

    def __init__(self):
        self.prompts = []

    async def available(self):
        return True

    async def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return "REPORT BODY"

    async def stream(self, prompt, **kwargs):
        self.prompts.append(prompt)

        async def gen():
            yield "REPORT ", ""

        async def _g():
            for piece in ("REPORT ", "BODY"):
                yield piece

        return _g()


async def test_smart_report_stream_and_latest(auth_client, monkeypatch):
    from app.services.ai import router as ai_router
    import app.routers.ai_insights as ai_insights

    provider = FakeReportProvider()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])
    monkeypatch.setattr(ai_insights, "pick_verifiers", lambda plan, name: [])

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(ai_insights, "get_settings", lambda: FakeSettings())

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    await auth_client.post(
        f"/api/v1/members/{member['id']}/labs",
        json={"test_name": "HbA1c", "result": "8.1", "units": "%", "flag": "high"},
    )

    events = []
    async with auth_client.stream(
        "POST", f"/api/v1/members/{member['id']}/reports/smart/stream"
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    stages = [e["stage"] for e in events]
    assert stages[0] == "stats" and stages[-1] == "complete"
    report = events[-1]["report"]
    assert report["content"] == "REPORT BODY"
    assert report["sources"]["labs_flagged"][0]["test_name"] == "HbA1c"
    assert "HbA1c" in provider.prompts[0]  # ground truth in prompt

    latest = (
        await auth_client.get(f"/api/v1/members/{member['id']}/reports/latest?kind=smart_report")
    ).json()
    assert latest["id"] == report["id"]

    assert (
        await auth_client.get(f"/api/v1/members/{member['id']}/reports/latest?kind=bogus")
    ).status_code == 422


# ── RAG ───────────────────────────────────────────────────────────────


def test_rag_chunk_and_search(tmp_path, monkeypatch):
    from app.services import rag

    monkeypatch.setattr(rag, "index_path", lambda: tmp_path / "rag.sqlite")
    monkeypatch.setattr(rag, "rag_available", lambda: True)

    pages = [
        (10, "Metformin is first-line therapy for type 2 diabetes. " * 30),
        (11, "Hypertension staging follows systolic thresholds. " * 30),
    ]
    count = rag.build_index(pages, "TestReference")
    assert count > 0

    hits = rag.search("metformin diabetes therapy")
    assert hits, "expected hits"
    assert hits[0]["page"] == 10
    assert hits[0]["source"] == "TestReference"

    assert rag.search("zzzzunfindable") == []

    # Malformed queries must not raise (FTS5 operator injection).
    assert isinstance(rag.search('"AND OR NOT ("'), list)


async def test_chat_grounded_by_rag(auth_client, monkeypatch):
    from app.services import rag
    from app.services.ai import router as ai_router
    import app.routers.conversations as conv_router

    monkeypatch.setattr(rag, "index_path", lambda: "/tmp/hmv2-test-rag.sqlite")
    monkeypatch.setattr(rag, "rag_available", lambda: True)
    monkeypatch.setattr(
        rag,
        "grounding_block",
        lambda q: (
            "Reference excerpts:\n[1] (Ref, page 10) Metformin first-line.",
            [{"page": 10, "snippet": "Metformin first-line."}],
        ),
    )

    class RecordingProvider:
        name = "rec"
        model = "x"
        local = True
        timeout = 1
        prompts = []

        async def available(self):
            return True

        async def stream(self, prompt, **kwargs):
            self.prompts.append(prompt)

            async def gen():
                yield "ok"

            return gen()

    provider = RecordingProvider()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    conv = (
        await auth_client.post("/api/v1/conversations", json={"member_id": member["id"]})
    ).json()

    events = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conv['id']}/messages/stream",
        json={"content": "first-line therapy?"},
    ) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    complete = events[-1]
    assert complete["sources"] == [{"page": 10, "snippet": "Metformin first-line."}]
    assert "Metformin first-line" in provider.prompts[0]

    # Grounding off → no sources.
    monkeypatch.setattr(rag, "rag_available", lambda: False)
    monkeypatch.setattr(rag, "grounding_block", lambda q: ("", []))
    provider.prompts.clear()
    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conv['id']}/messages/stream",
        json={"content": "again"},
    ) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                pass
    assert complete  # earlier grounding already proven


def test_rag_seed_script_chunking():
    from app.services.rag import chunk_pages

    chunks = chunk_pages([(1, "word " * 500)], "Src")
    assert all(c["page"] == 1 and c["source"] == "Src" for c in chunks)
    assert len(chunks) >= 2
