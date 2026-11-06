"""Ops layer: scheduler job idempotency, middleware stack, health endpoints.

Job bodies are called twice on seeded data everywhere — every one must be
double-run-safe (no duplicates, no exceptions).
"""

import os
import sqlite3
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.core.database import SessionLocal
from app.services import backup_service

# ── Helpers ───────────────────────────────────────────────────────────────


async def _notification_count(title_filter: str | None = None) -> int:
    from sqlalchemy import select

    from app.core.encryption import decrypt_secret
    from app.models import Notification

    async with SessionLocal() as db:
        rows = (await db.scalars(select(Notification))).all()
        titles = [(decrypt_secret(r.title_encrypted) or "").lower() for r in rows]
    if title_filter is None:
        return len(titles)
    return sum(1 for t in titles if title_filter.lower() in t)


async def _member_id(auth_client) -> str:
    resp = await auth_client.post("/api/v1/members", json={"name": "Asha"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


# ── Refill alerts ─────────────────────────────────────────────────────────


async def test_refill_alert_creates_one_then_zero(auth_client):
    from app.core import jobs

    member = await _member_id(auth_client)
    created = await auth_client.post(
        f"/api/v1/members/{member}/medications",
        json={"medicine": "Metformin", "schedule_type": "daily"},
    )
    assert created.status_code in (200, 201), created.text
    med_id = created.json()["id"]
    patched = await auth_client.patch(
        f"/api/v1/members/{member}/medications/{med_id}",
        json={"end_date": (date.today() + timedelta(days=3)).isoformat()},
    )
    assert patched.status_code == 200, patched.text

    first = await jobs.check_refill_alerts()
    assert first == 1
    assert await _notification_count("refill due") == 1

    second = await jobs.check_refill_alerts()
    assert second == 0
    assert await _notification_count("refill due") == 1  # no duplicate


async def test_refill_alert_skips_far_future_end(auth_client):
    from app.core import jobs

    member = await _member_id(auth_client)
    created = await auth_client.post(
        f"/api/v1/members/{member}/medications",
        json={"medicine": "Ibuprofen", "schedule_type": "daily"},
    )
    med_id = created.json()["id"]
    await auth_client.patch(
        f"/api/v1/members/{member}/medications/{med_id}",
        json={"end_date": (date.today() + timedelta(days=60)).isoformat()},
    )
    assert await jobs.check_refill_alerts() == 0


# ── Weekly digest ─────────────────────────────────────────────────────────


async def test_weekly_digest_idempotent(auth_client):
    from app.core import jobs

    member = await _member_id(auth_client)
    vital = await auth_client.post(
        f"/api/v1/members/{member}/vitals",
        json={
            "vital_type": "blood_pressure",
            "value_num": 118,
            "value_secondary": 76,
            "measured_at": datetime.now(UTC).isoformat(),
        },
    )
    assert vital.status_code == 201, vital.text

    first = await jobs.weekly_digest()
    assert first == 1
    assert await _notification_count("weekly health digest") == 1

    second = await jobs.weekly_digest()
    assert second == 0
    assert await _notification_count("weekly health digest") == 1


async def test_weekly_digest_silent_without_activity(auth_client):
    from app.core import jobs

    await _member_id(auth_client)  # household with a member, no data
    assert await jobs.weekly_digest() == 0
    assert await _notification_count() == 0


# ── Anomaly detection ─────────────────────────────────────────────────────


async def test_detect_anomalies_idempotent(auth_client):
    from app.core import jobs

    member = await _member_id(auth_client)
    vital = await auth_client.post(
        f"/api/v1/members/{member}/vitals",
        json={
            "vital_type": "blood_pressure",
            "value_num": 190,
            "value_secondary": 125,
            "measured_at": datetime.now(UTC).isoformat(),
        },
    )
    assert vital.status_code == 201, vital.text

    first = await jobs.detect_anomalies()
    assert first == 1
    assert await _notification_count("vital anomaly") == 1

    second = await jobs.detect_anomalies()
    assert second == 0
    assert await _notification_count("vital anomaly") == 1


async def test_detect_anomalies_ignores_normal_vitals(auth_client):
    from app.core import jobs

    member = await _member_id(auth_client)
    vital = await auth_client.post(
        f"/api/v1/members/{member}/vitals",
        json={
            "vital_type": "blood_pressure",
            "value_num": 115,
            "value_secondary": 75,
            "measured_at": datetime.now(UTC).isoformat(),
        },
    )
    assert vital.status_code == 201
    assert await jobs.detect_anomalies() == 0


async def test_detect_anomalies_glucose_high(auth_client):
    from app.core import jobs

    member = await _member_id(auth_client)
    vital = await auth_client.post(
        f"/api/v1/members/{member}/vitals",
        json={
            "vital_type": "blood_glucose",
            "value_num": 210,
            "glucose_context": "fasting",
            "measured_at": datetime.now(UTC).isoformat(),
        },
    )
    assert vital.status_code == 201
    assert await jobs.detect_anomalies() == 1
    assert await _notification_count("blood_glucose") == 1


# ── AI provider probe ─────────────────────────────────────────────────────


async def test_check_ai_providers_safe_and_repeatable():
    from app.core import jobs

    first = await jobs.check_ai_providers()
    # conftest points Ollama at a closed port and empties cloud keys.
    assert first.get("ollama") is False
    second = await jobs.check_ai_providers()
    assert second == first


# ── Backup rotation / state / round-trip ─────────────────────────────────


def _backup_dir() -> Path:
    backup_service.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return backup_service.BACKUPS_DIR


async def test_rotate_backups_prunes_old_only():
    from app.core import jobs

    bdir = _backup_dir()
    old = bdir / "backup_19990101_000000.tar.gz.enc"
    old.write_bytes(b"old")
    fresh = bdir / "backup_29990101_000000.tar.gz.enc"
    fresh.write_bytes(b"fresh")
    past = datetime.now().timestamp() - 40 * 86400
    os.utime(old, (past, past))
    try:
        assert await jobs.rotate_backups() >= 1
        assert not old.exists()
        assert fresh.exists()
        # Double run: nothing left to prune, fresh file survives.
        assert await jobs.rotate_backups() == 0
        assert fresh.exists()
    finally:
        fresh.unlink(missing_ok=True)


async def test_backup_database_gated_off_by_default(auth_client):
    from app.core import jobs

    # Households default to backup_schedule=off → no-op, no archive.
    before = {p.name for p in _backup_dir().glob("backup_*.tar.gz.enc")}
    assert await jobs.backup_database() is False
    after = {p.name for p in _backup_dir().glob("backup_*.tar.gz.enc")}
    assert before == after


async def test_backup_round_trip(auth_client):
    from app.core import jobs

    await _member_id(auth_client)  # seed a row we can count

    result = await jobs.run_backup_now()
    assert result is not None
    archive = backup_service.BACKUPS_DIR / result["filename"]
    assert archive.exists()
    try:
        tar_bytes = backup_service.read_backup(result["filename"])
        backup_service.validate_archive(tar_bytes)

        dest = backup_service.BACKUPS_DIR / f"restored_{uuid.uuid4().hex}.db"
        try:
            backup_service.restore_health_db(tar_bytes, dest)
            live_path = os.environ["DATABASE_URL"].replace("sqlite+aiosqlite:///", "")
            with sqlite3.connect(dest) as restored, sqlite3.connect(live_path) as live:
                restored_members = restored.execute(
                    "SELECT COUNT(*) FROM family_members"
                ).fetchone()[0]
                live_members = live.execute("SELECT COUNT(*) FROM family_members").fetchone()[0]
            assert restored_members == live_members >= 1
        finally:
            dest.unlink(missing_ok=True)

        # Second backup right away: allowed (run_backup_now is the ungated
        # path). Same-second archives share a timestamped name — that's fine.
        again = await jobs.run_backup_now()
        assert again is not None
        assert again["filename"].startswith("backup_")
        assert backup_service.read_backup_state().get("last_run")
    finally:
        for stale in backup_service.BACKUPS_DIR.glob("backup_*.tar.gz.enc"):
            stale.unlink(missing_ok=True)
        backup_service.STATE_FILE.unlink(missing_ok=True)


# ── Staging cleanup ───────────────────────────────────────────────────────


async def test_cleanup_staging_removes_stale_only():
    from app.core import jobs
    from app.core.storage import storage_root

    staging = storage_root().parent / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    stale = staging / "upload_old.tmp"
    stale.write_bytes(b"stale")
    fresh = staging / "upload_new.tmp"
    fresh.write_bytes(b"busy")
    past = datetime.now().timestamp() - 25 * 3600
    os.utime(stale, (past, past))
    try:
        assert await jobs.cleanup_staging() == 1
        assert not stale.exists()
        assert fresh.exists()
        # Double run: only the fresh file remains, nothing to do.
        assert await jobs.cleanup_staging() == 0
        assert fresh.exists()
    finally:
        fresh.unlink(missing_ok=True)


# ── File integrity ────────────────────────────────────────────────────────


async def test_verify_file_integrity_round_trip(auth_client):
    from app.core import jobs
    from app.core.storage import save_bytes
    from app.models import Attachment

    # Unique payload per run: the store dedups by hash, and data/attachments
    # persists across pytest invocations with different encryption keys.
    png = b"\x89PNG\r\n\x1a\n" + os.urandom(64)
    stored = save_bytes(png, "image/png")

    async with SessionLocal() as db:
        db.add(
            Attachment(
                record_id=uuid.uuid4(),  # FKs not enforced; job only reads paths
                file_path=stored.rel_path,
                content_hash=stored.content_hash,
                file_size=stored.size,
                mime=stored.mime,
                original_name=stored.content_hash,
            )
        )
        await db.commit()

    first = await jobs.verify_file_integrity()
    assert first["verified"] >= 1
    assert first["failed"] == 0
    # Double run: pure read, same result.
    assert await jobs.verify_file_integrity() == first


# ── Web push dispatch ─────────────────────────────────────────────────────


async def test_dispatch_web_push_disabled_noop(auth_client):
    from app.core import jobs

    assert (await jobs.dispatch_web_push())["disabled"] is True
    assert (await jobs.dispatch_web_push())["disabled"] is True  # double run


async def test_dispatch_pending_watermark_prunes_dispatched(auth_client, monkeypatch):
    from sqlalchemy import select

    from app.models import Household, PushSubscription
    from app.services import web_push_service
    from app.services.notifications import create_notification

    monkeypatch.setattr(web_push_service, "push_configured", lambda: True)
    resp = await auth_client.post(
        "/api/v1/notifications/push/subscribe",
        json={
            "endpoint": "https://push.example/op1",
            "keys": {"p256dh": "k", "auth": "a"},
        },
    )
    assert resp.status_code == 201, resp.text

    sends: list[str] = []

    def fake_send(subscription, title, message):
        sends.append(title)
        return True, False

    monkeypatch.setattr(web_push_service, "send_to_subscription", fake_send)

    async with SessionLocal() as db:
        household = (await db.scalars(select(Household))).one()
        create_notification(db, household_id=household.id, title="Watermark check", body="b")
        await db.commit()

    async with SessionLocal() as db:
        result1 = await web_push_service.dispatch_pending(db)
    assert result1["delivered"] == 1
    assert sends == ["Watermark check"]

    # Second run: the watermark advanced past the dispatched notification, so
    # nothing is re-sent ("prune dispatched watermarks" semantics).
    async with SessionLocal() as db:
        result2 = await web_push_service.dispatch_pending(db)
    assert result2["delivered"] == 0
    assert sends == ["Watermark check"]

    async with SessionLocal() as db:
        sub = (await db.scalars(select(PushSubscription))).one()
        assert sub.last_pushed_at is not None


# ── Scheduler single-instance lock ────────────────────────────────────────


def test_scheduler_lock_exclusive_and_lazy():
    from app.core import scheduler

    # Lock path created lazily — acquiring works, then a second holder fails.
    assert scheduler._try_acquire_scheduler_lock() is True
    try:
        assert scheduler._try_acquire_scheduler_lock() is False
    finally:
        scheduler._release_scheduler_lock()
    assert scheduler._try_acquire_scheduler_lock() is True
    scheduler._release_scheduler_lock()
    assert Path("data/scheduler.lock").parent.exists()


def test_start_scheduler_returns_none_when_locked(monkeypatch):
    from app.core import scheduler

    monkeypatch.setattr(scheduler, "_try_acquire_scheduler_lock", lambda: False)
    assert scheduler.start_scheduler() is None
    assert scheduler._scheduler is None


# ── Middleware stack (mini app — main.py wiring is the orchestrator's) ────


@pytest.fixture
async def mini_app():
    from fastapi import FastAPI

    from app.core.middleware import configure_middleware

    app = FastAPI()
    configure_middleware(app, hsts=False)

    from fastapi import Request

    @app.post("/api/v1/auth/login")
    async def login(request: Request) -> dict:
        await request.body()
        return {"ok": True}

    @app.get("/api/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    @app.post("/api/v1/anything")
    async def anything() -> dict:
        return {"ok": True}

    return app


async def _post(client, url, **kwargs):
    return await client.post(url, **kwargs)


async def test_rate_limit_auth_11th_request_429(mini_app):
    # conftest raises the env limits for the suite; pin v1's real numbers here.
    mini_app.state.auth_rate_limiter.limit = 10
    transport = httpx.ASGITransport(app=mini_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(10):
            resp = await _post(c, "/api/v1/auth/login", json={})
            assert resp.status_code == 200
        resp = await _post(c, "/api/v1/auth/login", json={})
        assert resp.status_code == 429
        assert "retry-after" in resp.headers


async def test_rate_limit_general_101st_request_429(mini_app):
    mini_app.state.general_rate_limiter.limit = 5  # retune in place
    transport = httpx.ASGITransport(app=mini_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        for i in range(5):
            resp = await c.get("/api/v1/ping")
            assert resp.status_code == 200
        resp = await c.get("/api/v1/ping")
        assert resp.status_code == 429


async def test_request_id_echoes_incoming(mini_app):
    transport = httpx.ASGITransport(app=mini_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/ping", headers={"X-Request-Id": "req-42"})
        assert resp.headers["X-Request-ID"] == "req-42"
        resp = await c.get("/api/v1/ping")
        assert resp.headers["X-Request-ID"]  # generated when absent


async def test_security_headers_present_no_hsts_by_default(mini_app):
    transport = httpx.ASGITransport(app=mini_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/ping")
        assert resp.headers["Content-Security-Policy"].startswith("default-src 'self'")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "strict-transport-security" not in resp.headers


async def test_hsts_when_enabled():
    from fastapi import FastAPI

    from app.core.middleware import configure_middleware

    app = FastAPI()
    configure_middleware(app, hsts=True)  # production wiring

    @app.get("/api/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/ping")
        assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


async def test_request_too_large_413(mini_app):
    transport = httpx.ASGITransport(app=mini_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/anything",
            content=b"x",
            headers={"Content-Length": str(60 * 1024 * 1024)},
        )
        assert resp.status_code == 413


# ── Health endpoints ──────────────────────────────────────────────────────


async def test_health_ready_ok(client):
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
    assert not (Path("data/attachments") / ".healthprobe").exists()


async def test_health_detail_forbidden_without_key(client):
    monkey_env = pytest.MonkeyPatch()
    monkey_env.delenv("HEALTH_KEY", raising=False)
    try:
        resp = await client.get("/api/v1/health/detail")
        assert resp.status_code == 403
    finally:
        monkey_env.undo()


async def test_health_detail_with_key(client, monkeypatch):
    monkeypatch.setenv("HEALTH_KEY", "ops-secret")
    resp = await client.get("/api/v1/health/detail", headers={"X-Health-Key": "ops-secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "counts" in body and "members" in body["counts"]

    wrong = await client.get("/api/v1/health/detail", headers={"X-Health-Key": "nope"})
    assert wrong.status_code == 403
