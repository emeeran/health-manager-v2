"""apply-extraction endpoint: structured data saved alongside the record.

Covers the consultation-flow contract: extraction JSON applied to a record
becomes (a) the record's clinical_data, (b) linked LabResult / Vital
Measurement rows, and (c) filled summary / diagnosis / date / doctor.
"""

import uuid


async def _member(client, name="Asha") -> str:
    return (await client.post("/api/v1/members", json={"name": name})).json()["id"]


async def _record(client, member_id: str, **overrides) -> dict:
    payload = {
        "record_type": "doctor_visit",
        "record_date": "2026-11-01",
        **overrides,
    }
    resp = await client.post(f"/api/v1/members/{member_id}/records", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_apply_extraction_persists_labs_and_vitals(auth_client):
    member_id = await _member(auth_client)
    record = await _record(auth_client, member_id)

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/apply-extraction",
        json={
            "clinical_data": {
                "medications": [{"name": "SYNDOPA 110mg", "dosage": "1-1-1", "duration_days": 30}],
                "labs": [
                    {
                        "name": "HbA1c",
                        "result": "7.8",
                        "units": "%",
                        "reference": "4.0-6.0",
                        "flag": "high",
                    }
                ],
                "vitals": [
                    {
                        "type": "blood_pressure",
                        "value": 150,
                        "value_secondary": 90,
                        "unit": "mmHg",
                    }
                ],
            },
            "summary": "Elevated HbA1c with uncontrolled hypertension.",
            "diagnosis": "Type 2 diabetes",
            "record_date": "2026-10-30",
            "doctor_name": "Dr Mehta",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["labs_created"] == 1
    assert body["vitals_created"] == 1

    # Structured data saved alongside the original record.
    got = await auth_client.get(f"/api/v1/members/{member_id}/records/{record['id']}")
    record = got.json()
    assert record["summary"].startswith("Elevated HbA1c")
    assert record["diagnosis"] == "Type 2 diabetes"
    assert record["record_date"] == "2026-10-30"
    assert record["doctor_name"] == "Dr Mehta"
    assert record["clinical_data"]["labs"][0]["name"] == "HbA1c"

    # Labs became queryable rows linked to the record.
    labs = (await auth_client.get(f"/api/v1/members/{member_id}/labs")).json()
    assert len(labs) == 1
    assert labs[0]["record_id"] == record["id"]
    assert labs[0]["test_name"] == "HbA1c"
    assert labs[0]["value_num"] == 7.8
    assert labs[0]["ref_low_num"] == 4.0
    assert labs[0]["ref_high_num"] == 6.0
    assert labs[0]["flag"] == "high"


async def test_apply_extraction_comparative_lab_dates(auth_client):
    """Per-lab dates win over the record's date (comparative lab tables)."""
    member_id = await _member(auth_client)
    record = await _record(auth_client, member_id)

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/apply-extraction",
        json={
            "clinical_data": {
                "labs": [
                    {"name": "Hemoglobin", "result": "9.2", "date": "2025-04-10"},
                    {"name": "Hemoglobin", "result": "7.8", "date": "2025-11-15"},
                    {"name": "TSH", "result": "1.23"},  # no date → record date
                ],
            },
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["labs_created"] == 3

    labs = (await auth_client.get(f"/api/v1/members/{member_id}/labs")).json()
    by_date = {lab["record_date"]: lab["result"] for lab in labs}
    assert by_date.get("2025-04-10") == "9.2"
    assert by_date.get("2025-11-15") == "7.8"
    assert by_date.get("2026-11-01") == "1.23"  # the record's own date

    # Idempotent re-apply: no duplicates even across the differing dates.
    again = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/apply-extraction",
        json={
            "clinical_data": {
                "labs": [
                    {"name": "Hemoglobin", "result": "9.2", "date": "2025-04-10"},
                    {"name": "Hemoglobin", "result": "7.8", "date": "2025-11-15"},
                ],
            },
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["labs_created"] == 0


async def test_apply_extraction_requires_matching_record(auth_client):
    member_id = await _member(auth_client)
    other = await _record(auth_client, member_id)
    member2 = await _member(auth_client, "Ravi")

    resp = await auth_client.post(
        f"/api/v1/members/{member2}/records/{other['id']}/apply-extraction",
        json={"clinical_data": {}},
    )
    assert resp.status_code == 404


async def test_medication_from_record_links_back(auth_client):
    member_id = await _member(auth_client)
    record = await _record(auth_client, member_id)

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/medications",
        json={
            "medicine": "SYNDOPA 110mg",
            "schedule_type": "daily",
            "record_id": record["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["record_id"] == record["id"]

    # A record from another member is rejected.
    member2 = await _member(auth_client, "Ravi")
    bad = await auth_client.post(
        f"/api/v1/members/{member2}/medications",
        json={
            "medicine": "X",
            "schedule_type": "daily",
            "record_id": record["id"],
        },
    )
    assert bad.status_code == 422


async def test_apply_extraction_rejects_unknown_record(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{uuid.uuid4()}/apply-extraction",
        json={"clinical_data": {}},
    )
    assert resp.status_code == 404


async def test_apply_extraction_merges_across_documents(auth_client):
    """Rx first, lab report second: sections accumulate instead of clobbering."""
    member_id = await _member(auth_client)
    record = await _record(auth_client, member_id)
    url = f"/api/v1/members/{member_id}/records/{record['id']}/apply-extraction"

    rx = await auth_client.post(
        url,
        json={
            "clinical_data": {
                "medications": [{"name": "SYNDOPA 110mg", "dosage": "1-1-1"}],
                "labs": [],
                "vitals": [],
            },
            "summary": "Prescription issued.",
        },
    )
    assert rx.status_code == 200, rx.text

    lab = await auth_client.post(
        url,
        json={
            "clinical_data": {
                "medications": [],
                "labs": [{"name": "CBC", "result": "normal", "flag": "normal"}],
            },
            "summary": "Labs attached.",
        },
    )
    assert lab.status_code == 200, lab.text

    got = await auth_client.get(f"/api/v1/members/{member_id}/records/{record['id']}")
    data = got.json()["clinical_data"]
    assert [m["name"] for m in data["medications"]] == ["SYNDOPA 110mg"]
    assert [lab["name"] for lab in data["labs"]] == ["CBC"]
    # Summary: the later document's text wins (explicitly provided).
    assert got.json()["summary"] == "Labs attached."


async def test_apply_extraction_keeps_glucose_context(auth_client):
    """FBG/PPBG/RBG tracking: the glucose context an extraction reports
    (fasting / post_prandial / random) reaches the VitalMeasurement row."""
    member_id = await _member(auth_client)
    record = await _record(auth_client, member_id)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/apply-extraction",
        json={
            "clinical_data": {
                "vitals": [
                    {
                        "type": "blood_glucose",
                        "value": 96,
                        "unit": "mg/dL",
                        "glucose_context": "fasting",
                    },
                    {
                        "type": "blood_glucose",
                        "value": 186,
                        "unit": "mg/dL",
                        "glucose_context": "post_prandial",
                    },
                ]
            },
            "record_date": "2026-11-01",
        },
    )
    assert resp.status_code == 200, resp.text
    listing = (
        await auth_client.get(f"/api/v1/members/{member_id}/vitals")
    ).json()
    glucose = [v for v in listing if v["vital_type"] == "blood_glucose"]
    assert sorted(v["glucose_context"] for v in glucose) == [
        "fasting",
        "post_prandial",
    ]
