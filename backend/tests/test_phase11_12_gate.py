"""Phase 11+12 gate e2e (tasklist §Phase 11, §Phase 12).

Phase 11 gate: consolidated report for a member with meds + labs; the
numbers in the narrative are grounded in DB-derived snapshot values, the
insight persists + latest-read round-trips, and flagged labs raise
health alerts at the extraction boundary.
Phase 12 gate: nightly backup archive appears and restores (round-trip).
"""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.services import health_alert_service

from app.services.ai import router as ai_router
from tests.test_ai_extraction import FakeProvider


NARRATIVE = (
    "Consolidated summary: HbA1c flagged high at 8.4 %; metformin 500 mg "
    "daily continues. Values are quoted from the attached snapshot."
)


@pytest.mark.asyncio
async def test_gate_consolidated_report_grounded(auth_client, monkeypatch):
    generator = FakeProvider(reply=NARRATIVE)
    verifier = FakeProvider(reply='{"verdict": "pass", "notes": ""}')
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [generator, verifier])

    member = (await auth_client.post("/api/v1/members", json={"name": "Gate II"})).json()
    member_id = member["id"]

    med = await auth_client.post(
        f"/api/v1/members/{member_id}/medications",
        json={
            "medicine": "Metformin",
            "dosage": "500 mg",
            "start_date": "2026-05-01",
        },
    )
    assert med.status_code == 201, med.text
    lab = await auth_client.post(
        f"/api/v1/members/{member_id}/labs",
        json={
            "test_name": "HbA1c",
            "value_num": 8.4,
            "units": "%",
            "flag": "high",
        },
    )
    assert lab.status_code == 201, lab.text

    stream = await auth_client.post(
        f"/api/v1/members/{member_id}/reports/consolidated-report/stream"
    )
    assert stream.status_code == 200, stream.text

    # Grounding invariant: the prompt the model saw carries the DB-derived
    # numbers — the narrative quotes them, the DB supplies them.
    prompt = generator.calls[0]["prompt"]
    assert "8.4" in prompt and "Metformin" in prompt

    latest = await auth_client.get(
        f"/api/v1/members/{member_id}/reports/consolidated-report/latest"
    )
    assert latest.status_code == 200, latest.text
    body = latest.json()
    assert body["content"] == NARRATIVE
    assert body["provider_used"] == "fake"

    # The lab anomaly also surfaces as a health alert at the extraction
    # boundary (labs POSTs are clinician-curated and alert only via
    # extraction, per the phase 11 design).
    import uuid as _uuid

    async with SessionLocal() as session:
        from sqlalchemy import select as _select

        from app.models import LabResult

        lab_row = (
            await session.scalars(
                _select(LabResult).where(LabResult.member_id == _uuid.UUID(member_id))
            )
        ).first()
        created = await health_alert_service.create_alerts_for_labs(
            session,
            member_id=_uuid.UUID(member_id),
            record_id=None,
            labs=[
                {
                    "test_name": lab_row.test_name,
                    "value_num": lab_row.value_num,
                    "units": lab_row.units,
                    "flag": lab_row.flag,
                    "reference": None,
                }
            ],
        )
        await session.commit()
    assert created, "flagged lab must create an alert"
    alerts = (await auth_client.get(f"/api/v1/members/{member_id}/health-alerts")).json()
    assert any(a["alert_type"] == "lab_anomaly" for a in alerts), alerts


@pytest.mark.asyncio
async def test_gate_backup_archive_appears_and_restores():
    from app.core import jobs
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import backup_service

    # backup_database() is schedule-gated; the gate exercises the archive
    # creation + restore path it delegates to.
    assert await jobs.run_backup_now() is not None

    archives = sorted(backup_service.BACKUPS_DIR.glob("*"))
    assert archives, "nightly backup archive must exist after the job runs"

    tar_bytes = backup_service.read_backup(archives[-1].name)
    dest = Path(tempfile.mkdtemp()) / "restored.db"
    backup_service.restore_health_db(tar_bytes, dest)
    assert dest.is_file() and dest.stat().st_size > 0

    # Round-trip: restored DB holds the same user rows as the live one.
    async with SessionLocal() as session:
        live_count = len((await session.scalars(select(User))).all())

    import sqlite3

    restored = sqlite3.connect(dest)
    try:
        restored_count = restored.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        restored.close()
    assert restored_count == live_count
