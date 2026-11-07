"""Medicine crawler toggle + scheduler job tests.

The crawler subprocess itself is never executed here — run_batch and the
stale-page requeue are monkeypatched or pointed at a throwaway SQLite file,
so these tests exercise toggle precedence, gating, and requeue logic only.
"""

import sqlite3

import pytest

from app.core import jobs
from app.services import medicine_crawler


async def test_crawler_toggle_default_off_and_roundtrip(auth_client):
    resp = await auth_client.get("/api/v1/system/medicine-crawler")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is False  # env default
    assert body["source"] == "default"

    resp = await auth_client.put("/api/v1/system/medicine-crawler", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
    assert resp.json()["source"] == "db"

    resp = await auth_client.get("/api/v1/system/medicine-crawler")
    assert resp.json()["enabled"] is True  # survives a fresh read

    resp = await auth_client.put("/api/v1/system/medicine-crawler", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


async def test_crawler_toggle_validates_body(auth_client):
    resp = await auth_client.put("/api/v1/system/medicine-crawler", json={})
    assert resp.status_code == 422
    resp = await auth_client.put(
        "/api/v1/system/medicine-crawler", json={"enabled": None}
    )
    assert resp.status_code == 422


async def test_job_disabled_by_default(monkeypatch):
    async def _explode(*a, **kw):  # must never be reached when disabled
        raise AssertionError("run_batch called while crawler disabled")

    monkeypatch.setattr(medicine_crawler, "run_batch", _explode)
    result = await jobs.crawl_medicine_catalog()
    assert result == {"status": "disabled"}


async def test_job_enabled_runs_batch(session_factory, monkeypatch):
    async def _fake_batch(limit, data_dir, timeout_seconds):
        assert limit > 0
        return {"status": "ok", "cmd": "crawl", "fetched": 10, "ok": 10, "err": 0}

    def _no_requeue(data_dir):  # sync: the real one runs via asyncio.to_thread
        return {"requeued": 0}

    monkeypatch.setattr(medicine_crawler, "run_batch", _fake_batch)
    monkeypatch.setattr(jobs, "_requeue_stale_pages", _no_requeue)

    async with session_factory() as db:
        await medicine_crawler.set_enabled(db, True)
        await db.commit()

    result = await jobs.crawl_medicine_catalog()
    assert result["status"] == "ok"
    assert result["requeued"] == 0


def test_requeue_stale_pages(tmp_path):
    db_path = tmp_path / "crawl.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE urls (url TEXT PRIMARY KEY, site TEXT, status TEXT, "
        "tries INTEGER DEFAULT 0, error TEXT, fetched_at REAL)"
    )
    old, fresh, pending = 1.0, (10 ** 10), None
    conn.executemany(
        "INSERT INTO urls (url, site, status, fetched_at) VALUES (?, ?, ?, ?)",
        [
            ("https://x/old", "1mg", "done", old),
            ("https://x/fresh", "1mg", "done", fresh),
            ("https://x/pending", "1mg", "pending", pending),
        ],
    )
    conn.commit()
    conn.close()

    requeued = jobs._requeue_stale_pages(str(tmp_path))
    assert requeued == {"requeued": 1}

    conn = sqlite3.connect(db_path)
    statuses = dict(conn.execute("SELECT url, status FROM urls").fetchall())
    conn.close()
    assert statuses["https://x/old"] == "pending"  # stale -> requeued
    assert statuses["https://x/fresh"] == "done"  # recent -> untouched
    assert statuses["https://x/pending"] == "pending"  # never queued twice


def test_requeue_noop_without_db(tmp_path):
    assert jobs._requeue_stale_pages(str(tmp_path)) == {"requeued": 0}


@pytest.mark.parametrize("payload", [{"status": "error", "detail": "boom"}, {"status": "timeout"}])
async def test_job_reports_crawler_failure_without_raising(
    session_factory, monkeypatch, payload
):
    async def _failing_batch(limit, data_dir, timeout_seconds):
        return dict(payload)

    def _no_requeue(data_dir):
        return {"requeued": 0}

    monkeypatch.setattr(medicine_crawler, "run_batch", _failing_batch)
    monkeypatch.setattr(jobs, "_requeue_stale_pages", _no_requeue)

    async with session_factory() as db:
        await medicine_crawler.set_enabled(db, True)
        await db.commit()

    result = await jobs.crawl_medicine_catalog()
    assert result["status"] == payload["status"]
