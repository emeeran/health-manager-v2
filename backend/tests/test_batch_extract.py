"""Phase 10: batch extraction SSE endpoint (fake provider, no network)."""

import json
import uuid
from typing import Any

import pytest

from app.services.ai import router as ai_router
from tests.test_thumbnails import make_png_bytes


class FakeProvider:
    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.model = "fake-model"
        self.local = name.startswith("local")
        self.timeout = 5
        self.calls: list[dict[str, Any]] = []

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return json.dumps(
            {
                "record_date": "2026-06-15",
                "doctor_name": "Dr. Batch",
                "diagnosis": "Hypertension",
                "summary": "Review in 3 months.",
                "medications": [],
                "labs": [],
                "vitals": [],
            }
        )


@pytest.fixture
def patch_plan(monkeypatch):
    def _patch(providers: list) -> None:
        monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: providers)

    return _patch


@pytest.fixture
def no_verification(monkeypatch):
    """Keep the batch stream deterministic: no background verifier."""
    from app.routers import extraction_batch

    monkeypatch.setattr(extraction_batch, "pick_verifiers", lambda plan, name: [])


@pytest.fixture(autouse=True)
def mount_batch_router(db_tables):
    from app.main import app
    from app.routers import extraction_batch

    existing = {getattr(r, "path", "") for r in app.routes}
    if not any(p.startswith("/api/v1/extract") for p in existing):
        app.include_router(extraction_batch.router, prefix="/api/v1")


@pytest.mark.asyncio
async def test_batch_stream_one_event_per_file(
    auth_client, patch_plan, no_verification, session_factory
):
    from sqlalchemy import select

    from app.models import HealthRecord

    patch_plan([FakeProvider()])
    member = await auth_client.post("/api/v1/members", json={"name": "Batchy"})
    member_id = member.json()["id"]

    files = [
        ("files", ("one.png", make_png_bytes(), "image/png")),
        ("files", ("two.png", make_png_bytes(), "image/png")),
        ("files", ("three.png", make_png_bytes(), "image/png")),
    ]
    events: list[dict] = []
    async with auth_client.stream(
        "POST", f"/api/v1/extract/batch/stream?member_id={member_id}", files=files
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    # One file_start + one complete per file, files processed in order.
    starts = [e for e in events if e["stage"] == "file_start"]
    completes = [e for e in events if e["stage"] == "complete"]
    assert [s["filename"] for s in starts] == ["one.png", "two.png", "three.png"]
    assert [c["filename"] for c in completes] == ["one.png", "two.png", "three.png"]
    assert [c["index"] for c in completes] == [0, 1, 2]
    assert all(c["total"] == 3 for c in completes)
    assert events[-1]["stage"] == "complete"

    # Each event carries a created record tagged with a content hash.
    record_ids = {c["result"]["record_id"] for c in completes}
    assert len(record_ids) == 3
    assert all(c["result"]["content_hash"] for c in completes)
    assert completes[0]["result"]["provider_used"] == "fake"
    assert completes[0]["result"]["clinical_data"]["diagnosis"] == "Hypertension"

    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(HealthRecord).where(HealthRecord.member_id == uuid.UUID(member_id))
            )
        ).all()
        assert len(rows) == 3
        assert {str(r.id) for r in rows} == record_ids
        for row in rows:
            assert row.content_hash  # tagged for dedup/merge
            assert row.summary == "Review in 3 months."

    # Same file content → identical payload → identical content_hash.
    hashes = {c["result"]["content_hash"] for c in completes}
    assert len(hashes) == 1


@pytest.mark.asyncio
async def test_batch_stream_survives_a_bad_file(auth_client, patch_plan, no_verification):
    patch_plan([FakeProvider()])
    member = await auth_client.post("/api/v1/members", json={"name": "Batchy2"})
    member_id = member.json()["id"]

    # A file with a disallowed mime fails per-file; the rest still complete.
    files = [
        ("files", ("good.png", make_png_bytes(), "image/png")),
        ("files", ("bad.txt", b"not an image", "text/plain")),
    ]
    events: list[dict] = []
    async with auth_client.stream(
        "POST", f"/api/v1/extract/batch/stream?member_id={member_id}", files=files
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    errors = [e for e in events if e["stage"] == "error"]
    completes = [e for e in events if e["stage"] == "complete"]
    assert len(completes) == 1
    assert completes[0]["filename"] == "good.png"
    assert len(errors) == 1
    assert errors[0]["filename"] == "bad.txt"
    assert errors[0]["message"]  # reason surfaced


@pytest.mark.asyncio
async def test_batch_stream_requires_auth():
    from tests.test_household_admin import _extra_client

    async with _extra_client() as anon:
        resp = await anon.post(
            "/api/v1/extract/batch/stream",
            files=[("files", ("x.png", make_png_bytes(), "image/png"))],
        )
    assert resp.status_code == 401
