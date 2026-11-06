"""Phase 9: people breadth — providers, assignments/UHID, insurance,
emergency card, history feed, encrypted member fields, record→provider link."""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.models import FamilyMember

# ── helpers ───────────────────────────────────────────────────────────


async def _create_member(client, name: str = "Asha") -> dict:
    resp = await client.post("/api/v1/members", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_provider(client, name: str = "Dr Rao") -> dict:
    resp = await client.post(
        "/api/v1/providers",
        json={"name": name, "specialty": "Cardiology", "hospital": "City Hosp"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── provider directory ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_crud_and_phone_encrypted(auth_client, session_factory):
    created = await _create_provider(auth_client, "Dr Rao")
    assert created["phone"] is None

    updated = await auth_client.patch(
        f"/api/v1/providers/{created['id']}", json={"phone": "+91-9876543210"}
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+91-9876543210"  # decrypted on read

    # Encrypted at rest (raw SQL — the ORM type decrypts transparently).
    from sqlalchemy import text

    async with session_factory() as session:
        raw = await session.execute(
            text("SELECT phone FROM providers WHERE id = :id"),
            {"id": uuid.UUID(created["id"]).hex},
        )
        stored = raw.scalar_one()
        assert stored.startswith("gAAAA")  # Fernet token
        assert stored != "+91-9876543210"

    listed = (await auth_client.get("/api/v1/providers")).json()
    assert [p["name"] for p in listed] == ["Dr Rao"]

    deleted = await auth_client.delete(f"/api/v1/providers/{created['id']}")
    assert deleted.status_code == 204
    assert (await auth_client.get("/api/v1/providers")).json() == []


@pytest.mark.asyncio
async def test_provider_scoped_to_household(auth_client):
    await _create_provider(auth_client)
    stranger = uuid.uuid4()
    resp = await auth_client.patch(f"/api/v1/providers/{stranger}", json={"name": "X"})
    assert resp.status_code == 404


# ── assignments ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assignment_lifecycle_with_uhid(auth_client):
    member = await _create_member(auth_client)
    provider = await _create_provider(auth_client)

    assigned = await auth_client.post(
        f"/api/v1/members/{member['id']}/providers",
        json={"provider_id": provider["id"], "uhid": "CITY-00123"},
    )
    assert assigned.status_code == 201
    body = assigned.json()
    assert body["provider_name"] == "Dr Rao"
    assert body["uhid"] == "CITY-00123"

    # Duplicate assignment is rejected (unique pair).
    dup = await auth_client.post(
        f"/api/v1/members/{member['id']}/providers",
        json={"provider_id": provider["id"]},
    )
    assert dup.status_code == 409

    assignment_id = body["id"]
    patched = await auth_client.patch(
        f"/api/v1/members/{member['id']}/providers/{assignment_id}",
        json={"uhid": "CITY-00999"},
    )
    assert patched.json()["uhid"] == "CITY-00999"

    listed = (await auth_client.get(f"/api/v1/members/{member['id']}/providers")).json()
    assert len(listed) == 1
    assert listed[0]["uhid"] == "CITY-00999"

    removed = await auth_client.delete(f"/api/v1/members/{member['id']}/providers/{assignment_id}")
    assert removed.status_code == 204
    assert (await auth_client.get(f"/api/v1/members/{member['id']}/providers")).json() == []


@pytest.mark.asyncio
async def test_assignment_requires_known_provider(auth_client):
    member = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member['id']}/providers",
        json={"provider_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# ── records reference providers ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_can_reference_provider(auth_client):
    member = await _create_member(auth_client)
    provider = await _create_provider(auth_client)

    created = await auth_client.post(
        f"/api/v1/members/{member['id']}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-11-01",
            "summary": "Checkup",
            "provider_id": provider["id"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["provider_name"] == "Dr Rao"

    fetched = await auth_client.get(
        f"/api/v1/members/{member['id']}/records/{created.json()['id']}"
    )
    assert fetched.json()["provider_name"] == "Dr Rao"

    # Unknown provider → 404, record not created.
    bad = await auth_client.post(
        f"/api/v1/members/{member['id']}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-11-01",
            "provider_id": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 404


# ── insurance ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_and_claim_lifecycle(auth_client, session_factory):
    member = await _create_member(auth_client, "Insured")

    policy = await auth_client.post(
        f"/api/v1/members/{member['id']}/insurance/policies",
        json={
            "insurer": "Star Health",
            "plan_name": "Family Optima",
            "policy_number": "POL-123456",
            "sum_insured": 500000,
            "valid_till": "2027-03-31",
        },
    )
    assert policy.status_code == 201, policy.text
    assert policy.json()["policy_number"] == "POL-123456"

    # Policy number encrypted at rest (raw SQL — ORM reads decrypt).
    from sqlalchemy import text

    async with session_factory() as session:
        raw = await session.execute(text("SELECT policy_number FROM insurance_policies LIMIT 1"))
        assert raw.scalar_one().startswith("gAAAA")

    policy_id = policy.json()["id"]
    claim = await auth_client.post(
        f"/api/v1/members/{member['id']}/insurance/policies/{policy_id}/claims",
        json={
            "amount": 12500.50,
            "claimed_on": "2026-11-01",
            "description": "Hospitalisation",
        },
    )
    assert claim.status_code == 201
    claim_id = claim.json()["id"]

    advanced = await auth_client.patch(
        f"/api/v1/members/{member['id']}/insurance/policies/{policy_id}/claims/{claim_id}",
        json={"status": "approved"},
    )
    assert advanced.json()["status"] == "approved"

    claims = (
        await auth_client.get(
            f"/api/v1/members/{member['id']}/insurance/policies/{policy_id}/claims"
        )
    ).json()
    assert len(claims) == 1 and claims[0]["status"] == "approved"

    removed = await auth_client.delete(
        f"/api/v1/members/{member['id']}/insurance/policies/{policy_id}"
    )
    assert removed.status_code == 204


# ── emergency card ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emergency_card_payload(auth_client):
    from app.core.database import SessionLocal
    from app.models import Allergy, ConditionEpisode, Medication

    member = await _create_member(auth_client, "ICE")
    member_id = uuid.UUID(member["id"])
    await auth_client.patch(
        f"/api/v1/members/{member_id}",
        json={
            "blood_group": "O+",
            "emergency_contact_name": "Meeran",
            "emergency_contact_phone": "+91-90000-00000",
        },
    )
    provider = await _create_provider(auth_client)
    await auth_client.post(
        f"/api/v1/members/{member_id}/providers",
        json={"provider_id": provider["id"], "uhid": "U-1"},
    )

    async with SessionLocal() as session:
        session.add_all(
            [
                Allergy(member_id=member_id, substance="Penicillin", severity="severe"),
                ConditionEpisode(member_id=member_id, name="Asthma", status="chronic"),
                Medication(
                    member_id=member_id,
                    medicine="Salbutamol",
                    medicine_key="salbutamol",
                    dosage="2 puffs PRN",
                    status="active",
                ),
            ]
        )
        await session.commit()

    card = (await auth_client.get(f"/api/v1/members/{member_id}/emergency")).json()
    assert card["member"]["blood_group"] == "O+"
    assert card["member"]["emergency_contact_name"] == "Meeran"
    assert card["allergies"] == [
        {"substance": "Penicillin", "severity": "severe", "reaction": None}
    ]
    assert card["conditions"] == [{"name": "Asthma", "status": "chronic"}]
    assert card["active_medications"] == [{"medicine": "Salbutamol", "dosage": "2 puffs PRN"}]
    assert card["providers"][0]["uhid"] == "U-1"


# ── history feed ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_history_feed_merges_domains(auth_client):
    from app.core.database import SessionLocal
    from app.models import LabResult, VitalMeasurement

    member = await _create_member(auth_client, "History")
    mid = uuid.UUID(member["id"])

    record = await auth_client.post(
        f"/api/v1/members/{mid}/records",
        json={"record_type": "lab_report", "record_date": "2026-10-01", "summary": "Panel"},
    )
    assert record.status_code == 201

    async with SessionLocal() as session:
        session.add_all(
            [
                LabResult(
                    member_id=mid,
                    test_name="HbA1c",
                    result="6.1",
                    units="%",
                    record_date=date(2026, 10, 2),
                ),
                VitalMeasurement(
                    member_id=mid,
                    vital_type="blood_pressure",
                    value_num=120,
                    value_secondary=80,
                    unit="mmHg",
                    measured_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()

    feed = (await auth_client.get(f"/api/v1/members/{mid}/history")).json()
    types = [item["type"] for item in feed]
    assert set(types) == {"record", "lab", "vital"}
    # Newest first.
    dates = [item["date"] for item in feed]
    assert dates == sorted(dates, reverse=True)
    vital = next(i for i in feed if i["type"] == "vital")
    assert vital["title"] == "Blood Pressure: 120.0/80.0 mmHg"


# ── member encrypted fields ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_member_phi_fields_encrypted_at_rest(auth_client, session_factory):
    member = await _create_member(auth_client, "Secret")
    mid = uuid.UUID(member["id"])

    updated = await auth_client.patch(
        f"/api/v1/members/{mid}",
        json={
            "phone": "+91-9111111111",
            "address": "12 Safe Street",
            "medical_history": "Hypertension since 2020",
            "blood_group": "A-",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+91-9111111111"

    async with session_factory() as session:
        row = await session.get(FamilyMember, mid)
        # ORM reads decrypt transparently — check the decrypted values…
        assert row.phone == "+91-9111111111"
        assert row.medical_history == "Hypertension since 2020"
        # …and the at-rest ciphertext via raw SQL.
        from sqlalchemy import text

        raw = await session.execute(
            text("SELECT phone, address, blood_group FROM family_members WHERE id = :id"),
            {"id": mid.hex},
        )
        stored_phone, stored_address, stored_group = raw.one()
        assert stored_phone.startswith("gAAAA")
        assert stored_address.startswith("gAAAA")
        assert stored_group == "A-"  # not sensitive, stored plain
