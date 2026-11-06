"""Phase 10 gate e2e (tasklist §Phase 10).

Gate 1: upload record → extract → flag duplicate → merge (idempotent).
Gate 2: add allergy → prescribe conflicting med → conflict surfaces
        (the Safety tab's data source).
Also exercises the integrity card over the mutated database.
"""

import json
import uuid

import pytest

from app.services.ai import router as ai_router
from tests.test_ai_extraction import FakeProvider, patch_plan  # noqa: F401
from tests.test_thumbnails import make_png_bytes


async def _make_member(client) -> str:
    response = await client.post("/api/v1/members", json={"name": "Gate Kid"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_gate_extract_duplicate_merge(auth_client, monkeypatch):
    provider = FakeProvider(
        reply=json.dumps(
            {
                "record_date": "2026-05-10",
                "doctor_name": "Dr. Gate",
                "diagnosis": "Asthma follow-up",
                "summary": "Review inhaler technique.",
                "medications": [],
                "labs": [],
                "vitals": [],
            }
        )
    )
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])

    member_id = await _make_member(auth_client)

    # 1. Upload + extract (parsed draft only — record creation is explicit).
    png = make_png_bytes()
    extracted = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files={"file": ("visit1.png", png, "image/png")},
    )
    assert extracted.status_code == 200, extracted.text
    parsed = extracted.json()
    # clinical_data arrives as a JSON string from the extraction service.
    clinical = (
        json.loads(parsed["clinical_data"])
        if isinstance(parsed["clinical_data"], str)
        else parsed["clinical_data"]
    )
    assert clinical, parsed

    # 2. Save the extracted draft, then re-save an identical payload —
    #    both records get the same content_hash → duplicate pair.
    record_ids = []
    for _ in range(2):
        saved = await auth_client.post(
            f"/api/v1/members/{member_id}/records",
            json={
                "record_type": "doctor_visit",
                "record_date": clinical["record_date"],
                "clinical_data": clinical,
                "summary": parsed["summary"],
            },
        )
        assert saved.status_code == 201, saved.text
        record_ids.append(saved.json()["id"])
    record_id, dup_id = record_ids
    assert record_id != dup_id

    candidates = await auth_client.get(f"/api/v1/members/{member_id}/records/duplicates")
    assert candidates.status_code == 200, candidates.text
    pairs = candidates.json()["pairs"]
    assert any({p["primary_id"], p["duplicate_id"]} == {record_id, dup_id} for p in pairs), pairs

    # 3. Merge the duplicate into the primary (path record is the one
    #    absorbed; `duplicate_of_id` is the survivor).
    merged = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{dup_id}/merge",
        json={"duplicate_of_id": record_id},
    )
    assert merged.status_code in (200, 204), merged.text

    listing = (await auth_client.get(f"/api/v1/members/{member_id}/records")).json()
    ids = {r["id"] for r in listing}
    assert record_id in ids and dup_id not in ids

    # 4. Idempotent: re-merge is a no-op success.
    again = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{dup_id}/merge",
        json={"duplicate_of_id": record_id},
    )
    assert again.status_code in (200, 204), again.text

    # The merged duplicate is hidden from the API (404) — verify its
    # merge marker directly in the DB instead.
    from sqlalchemy import select

    from app.core.database import engine
    from app.models import HealthRecord

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(HealthRecord.merged_into_id).where(HealthRecord.id == uuid.UUID(dup_id))
            )
        ).scalar_one()
    assert row == uuid.UUID(record_id)


@pytest.mark.asyncio
async def test_gate_allergy_conflict_surfaces(auth_client):
    member_id = await _make_member(auth_client)

    allergy = await auth_client.post(
        f"/api/v1/members/{member_id}/allergies",
        json={"substance": "Aspirin", "severity": "severe"},
    )
    assert allergy.status_code == 201, allergy.text

    med = await auth_client.post(
        f"/api/v1/members/{member_id}/medications",
        json={"medicine": "Aspirin", "start_date": "2026-05-01"},
    )
    assert med.status_code == 201, med.text
    med_id = med.json()["id"]

    # Active med → conflict surfaces.
    conflicts = await auth_client.get(f"/api/v1/members/{member_id}/allergy-conflicts")
    assert conflicts.status_code == 200, conflicts.text
    hits = [c for c in conflicts.json() if c["medication"] == "Aspirin"]
    assert len(hits) == 1, conflicts.text
    assert hits[0]["allergy"] == "Aspirin"
    assert hits[0]["matched_on"] == "medicine_name"

    # Once the med is stopped, the conflict clears.
    stopped = await auth_client.patch(
        f"/api/v1/members/{member_id}/medications/{med_id}",
        json={"status": "stopped"},
    )
    assert stopped.status_code == 200, stopped.text
    conflicts = await auth_client.get(f"/api/v1/members/{member_id}/allergy-conflicts")
    assert conflicts.json() == [], conflicts.text

    # The Safety tab's other input: integrity card still clean after the
    # gate's writes.
    integrity = await auth_client.get("/api/v1/database/integrity")
    assert integrity.status_code == 200, integrity.text
    assert integrity.json()["ok"] is True
