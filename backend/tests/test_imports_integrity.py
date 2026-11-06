"""Phase 10: FHIR import, Apple Health import, database integrity card.

Routers under test live in their own modules (the orchestrator mounts
them in app/main.py); the ``mount_import_routers`` fixture registers them
idempotently so the suite also passes standalone.
"""

import uuid
from datetime import UTC, datetime

import pytest

# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mount_import_routers(db_tables):
    from app.main import app

    from app.routers import database, fhir_import, health_import

    existing = {getattr(r, "path", "") for r in app.routes}
    for module_router in (
        database.router,
        fhir_import.router,
        health_import.router,
    ):
        prefix = f"/api/v1{module_router.prefix}"
        if not any(path.startswith(prefix) for path in existing):
            app.include_router(module_router, prefix="/api/v1")


async def _create_member(client, name: str = "Importer") -> str:
    resp = await client.post("/api/v1/members", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── FHIR import ───────────────────────────────────────────────────────


def _fhir_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "name": [{"text": "Ignore me"}],
                }
            },
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "code": {"text": "Penicillin"},
                    "criticality": "high",
                    "reaction": [
                        {
                            "manifestation": [
                                {"text": "Hives"},
                            ],
                            "severity": "severe",
                        }
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {"text": "Type 2 Diabetes Mellitus"},
                    "clinicalStatus": {
                        "coding": [{"code": "active"}],
                    },
                    "onsetDateTime": "2024-03-01",
                }
            },
            {
                "resource": {
                    "resourceType": "Immunization",
                    "vaccineCode": {"text": "Influenza vaccine"},
                    "occurrenceDateTime": "2025-10-05",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"text": "Body Weight"},
                    "valueQuantity": {"value": 72.4, "unit": "kg"},
                    "effectiveDateTime": "2026-01-10T08:00:00Z",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"text": "Blood pressure panel"},
                    "effectiveDateTime": "2026-01-10T09:00:00Z",
                    "component": [
                        {
                            "code": {"text": "Systolic blood pressure"},
                            "valueQuantity": {"value": 122, "unit": "mmHg"},
                        },
                        {
                            "code": {"text": "Diastolic blood pressure"},
                            "valueQuantity": {"value": 81, "unit": "mmHg"},
                        },
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "medicationCodeableConcept": {"text": "Metformin"},
                    "authoredOn": "2024-03-02",
                    "dosageInstruction": [{"text": "500 mg twice daily"}],
                }
            },
            {
                "resource": {
                    "resourceType": "DiagnosticReport",
                    "code": {"text": "HbA1c panel"},
                    "conclusion": "6.4 percent",
                    "effectiveDateTime": "2024-03-05",
                }
            },
        ],
    }


@pytest.mark.asyncio
async def test_fhir_import_creates_and_is_idempotent(auth_client, mount_import_routers):
    from app.core.database import SessionLocal
    from app.models import (
        Allergy,
        ConditionEpisode,
        HealthRecord,
        LabResult,
        Medication,
        VitalMeasurement,
    )

    member_id = await _create_member(auth_client)
    url = f"/api/v1/members/{member_id}/import/fhir"

    first = await auth_client.post(url, json=_fhir_bundle())
    assert first.status_code == 200, first.text
    created = first.json()["created"]
    assert created == {
        "allergies": 1,
        "conditions": 1,
        "vaccinations": 1,
        "vitals": 2,  # weight + merged BP
        "medications": 1,
        "labs": 1,
    }

    # Rows landed where they should, with BP paired into one row.
    async with SessionLocal() as session:
        from sqlalchemy import select

        allergy_rows = (await session.scalars(select(Allergy))).all()
        assert allergy_rows[0].substance == "Penicillin"
        assert allergy_rows[0].severity == "severe"
        assert allergy_rows[0].reaction == "Hives"

        condition_rows = (await session.scalars(select(ConditionEpisode))).all()
        assert condition_rows[0].name == "Type 2 Diabetes Mellitus"
        assert condition_rows[0].status == "active"

        vaccination_rows = (
            await session.scalars(
                select(HealthRecord).where(HealthRecord.record_type == "vaccination")
            )
        ).all()
        assert len(vaccination_rows) == 1
        assert vaccination_rows[0].summary == "Influenza vaccine"
        assert vaccination_rows[0].content_hash

        vitals = (await session.scalars(select(VitalMeasurement))).all()
        bp = next(v for v in vitals if v.vital_type == "blood_pressure")
        assert (bp.value_num, bp.value_secondary) == (122.0, 81.0)
        weight = next(v for v in vitals if v.vital_type == "weight")
        assert weight.value_num == 72.4
        assert all(v.source == "fhir_import" for v in vitals)

        meds = (await session.scalars(select(Medication))).all()
        assert meds[0].medicine == "Metformin"
        assert meds[0].medicine_key == "metformin"

        labs = (await session.scalars(select(LabResult))).all()
        assert labs[0].test_name == "HbA1c panel"

    # Re-import: everything skipped as already present.
    second = await auth_client.post(url, json=_fhir_bundle())
    assert second.status_code == 200
    body = second.json()
    assert body["created"] == {}
    assert body["skipped_existing"] == {
        "allergies": 1,
        "conditions": 1,
        "vaccinations": 1,
        "vitals": 2,
        "medications": 1,
        "labs": 1,
    }


@pytest.mark.asyncio
async def test_fhir_import_rejects_bad_bundles(auth_client, mount_import_routers):
    member_id = await _create_member(auth_client)
    url = f"/api/v1/members/{member_id}/import/fhir"

    not_json = await auth_client.post(
        url, content=b"hello", headers={"Content-Type": "application/json"}
    )
    assert not_json.status_code == 422
    not_bundle = await auth_client.post(url, json={"resourceType": "Patient"})
    assert not_bundle.status_code == 422
    # Unauthenticated → 401.
    from tests.test_household_admin import _extra_client

    async with _extra_client() as anon:
        anon_resp = await anon.post(url, json=_fhir_bundle())
    assert anon_resp.status_code == 401


# ── Apple Health import ───────────────────────────────────────────────


def _apple_health_xml() -> bytes:
    records = [
        # Two weight samples on the same day → one daily mean row.
        ("HKQuantityTypeIdentifierBodyMass", "72.6", "kg", "2026-02-01T07:30:00Z"),
        ("HKQuantityTypeIdentifierBodyMass", "72.4", "kg", "2026-02-01T22:00:00Z"),
        # Heart rate samples on the same day → one daily mean row.
        ("HKQuantityTypeIdentifierHeartRate", "61", "count/min", "2026-02-01T10:00:00Z"),
        ("HKQuantityTypeIdentifierHeartRate", "69", "count/min", "2026-02-01T18:00:00Z"),
        # BP systolic + diastolic on the same day → one paired row.
        ("HKQuantityTypeIdentifierBloodPressureSystolic", "118", "mmHg", "2026-02-02T08:00:00Z"),
        ("HKQuantityTypeIdentifierBloodPressureDiastolic", "76", "mmHg", "2026-02-02T08:00:00Z"),
        # Fractional SpO2 → normalized to percent.
        ("HKQuantityTypeIdentifierOxygenSaturation", "0.97", "%", "2026-02-02T09:00:00Z"),
        # Unknown type + bad values → skipped, not fatal.
        ("HKQuantityTypeIdentifierStepCount", "4321", "count", "2026-02-02T09:00:00Z"),
        ("HKQuantityTypeIdentifierBodyMass", "not-a-number", "kg", "2026-02-03T09:00:00Z"),
    ]
    lines = ['<?xml version="1.0"?><HealthData locale="en">']
    for rtype, value, unit, start in records:
        lines.append(
            f'<Record type="{rtype}" value="{value}" unit="{unit}" '
            f'startDate="{start}" sourceName="Apple Watch"/>'
        )
    lines.append("</HealthData>")
    return "\n".join(lines).encode()


@pytest.mark.asyncio
async def test_apple_health_import_vitals_bp_and_dedupe(auth_client, mount_import_routers):
    from app.core.database import SessionLocal
    from sqlalchemy import select

    from app.models import VitalMeasurement

    member_id = await _create_member(auth_client, "Apple")
    url = f"/api/v1/members/{member_id}/import/apple-health"

    first = await auth_client.post(
        url, files={"file": ("Export.xml", _apple_health_xml(), "application/xml")}
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] == 4  # weight, heart_rate, blood_pressure, spo2
    assert body["updated"] == 0

    async with SessionLocal() as session:
        rows = (await session.scalars(select(VitalMeasurement))).all()
        by_type = {r.vital_type: r for r in rows}
        assert len(rows) == 4
        weight = by_type["weight"]
        assert weight.value_num == 72.5  # mean(72.6, 72.4)
        hr = by_type["heart_rate"]
        assert hr.value_num == 65.0  # mean(61, 69)
        bp = by_type["blood_pressure"]
        assert bp.value_num == 118.0
        assert bp.value_secondary == 76.0
        spo2 = by_type["spo2"]
        assert spo2.value_num == 97.0  # fractional normalized
        for row in rows:
            assert row.source == "health_import"
            assert row.measured_at.date().isoformat() in ("2026-02-01", "2026-02-02")

    # Re-upload the same export → fully deduped, values updated in place.
    second = await auth_client.post(
        url, files={"file": ("Export.xml", _apple_health_xml(), "application/xml")}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["created"] == 0
    assert body["updated"] == 4

    async with SessionLocal() as session:
        rows = (await session.scalars(select(VitalMeasurement))).all()
        assert len(rows) == 4  # no duplicates created


@pytest.mark.asyncio
async def test_apple_health_rejects_garbage(auth_client, mount_import_routers):
    member_id = await _create_member(auth_client, "Garbage")
    url = f"/api/v1/members/{member_id}/import/apple-health"
    bad = await auth_client.post(
        url, files={"file": ("Export.xml", b"<html>not health</html>", "application/xml")}
    )
    # Garbage parses to zero records (no crash, nothing created).
    assert bad.status_code == 200, bad.text
    assert bad.json()["created"] == 0
    empty = await auth_client.post(url, files={"file": ("Export.xml", b"", "application/xml")})
    assert empty.status_code == 422


# ── database integrity card ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_integrity_clean_db(auth_client, mount_import_routers):
    resp = await auth_client.get("/api/v1/database/integrity")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["integrity_check"] == ["ok"]
    assert body["orphan_count"] == 0
    assert body["attachment_check"]["checked"] == 0
    assert body["attachment_check"]["missing"] == 0


@pytest.mark.asyncio
async def test_integrity_detects_hand_inserted_orphan(
    auth_client, mount_import_routers, session_factory
):
    from app.models import VitalMeasurement

    async with session_factory() as session:
        session.add(
            VitalMeasurement(
                member_id=uuid.uuid4(),  # no such member — an orphan row
                vital_type="weight",
                value_num=80.0,
                measured_at=datetime.now(UTC),
            )
        )
        await session.commit()

    resp = await auth_client.get("/api/v1/database/integrity")
    assert resp.status_code == 200
    body = resp.json()
    # Orphans are data hygiene, not corruption: ok stays True.
    assert body["ok"] is True
    assert body["orphan_count"] >= 1
    vital_orphans = [o for o in body["orphans"] if o["table"] == "vital_measurements"]
    assert vital_orphans and vital_orphans[0]["count"] >= 1


@pytest.mark.asyncio
async def test_integrity_requires_auth(mount_import_routers):
    from tests.test_household_admin import _extra_client

    async with _extra_client() as anon:
        resp = await anon.get("/api/v1/database/integrity")
    assert resp.status_code == 401
