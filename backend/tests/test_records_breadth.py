"""Phase 10 breadth tests: conditions, allergies, symptoms, vaccinations,
immunizations/milestones, and the CDC growth report.

The routers under test are wired here into a local FastAPI app (the
orchestrator registers them in app.main); auth + member + vitals +
medications + labs + records routers are included so fixtures ride the
real endpoints. No AI providers are touched.
"""

from datetime import date, datetime, time, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core.database import SessionLocal


def _test_app() -> FastAPI:
    from app.routers import (
        allergies,
        auth,
        conditions,
        growth,
        immunizations,
        labs,
        medications,
        members,
        records,
        symptoms,
        vaccinations,
        vitals,
    )

    app = FastAPI()
    for router in (
        auth.router,
        members.router,
        vitals.router,
        medications.router,
        labs.router,
        records.router,
        conditions.router,
        allergies.router,
        allergies.conflicts_router,
        symptoms.router,
        vaccinations.router,
        immunizations.router,
        growth.router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


@pytest_asyncio.fixture
async def api(db_tables):
    app = _test_app()

    async def _override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    from app.core.database import get_db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_api(api):
    register = await api.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "TestPass1!"},
    )
    assert register.status_code == 200, register.text
    return api


# ── helpers ───────────────────────────────────────────────────────────


async def _member(client, name: str = "Asha", birth_date: str | None = None) -> dict:
    payload: dict = {"name": name}
    if birth_date:
        payload["birth_date"] = birth_date
    resp = await client.post("/api/v1/members", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _vital(client, member_id: str, vital_type: str, value: float, day: date) -> dict:
    resp = await client.post(
        f"/api/v1/members/{member_id}/vitals",
        json={
            "vital_type": vital_type,
            "value_num": value,
            "measured_at": datetime.combine(day, time(9, 0), tzinfo=timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _medication(client, member_id: str, medicine: str, **kwargs) -> dict:
    resp = await client.post(
        f"/api/v1/members/{member_id}/medications",
        json={"medicine": medicine, **kwargs},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _allergy(client, member_id: str, substance: str, **kwargs) -> dict:
    resp = await client.post(
        f"/api/v1/members/{member_id}/allergies",
        json={"substance": substance, **kwargs},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── conditions ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_condition_course_invariants(auth_api):
    c = auth_api
    member = await _member(c)

    # resolution before onset
    resp = await c.post(
        f"/api/v1/members/{member['id']}/conditions",
        json={"name": "Flu", "onset_date": "2026-01-10", "resolution_date": "2026-01-05"},
    )
    assert resp.status_code == 422

    # resolved without a resolution date
    resp = await c.post(
        f"/api/v1/members/{member['id']}/conditions",
        json={"name": "Flu", "status": "resolved"},
    )
    assert resp.status_code == 422

    # valid create
    resp = await c.post(
        f"/api/v1/members/{member['id']}/conditions",
        json={
            "name": "Type 2 Diabetes",
            "icd10_code": "E11.9",
            "status": "chronic",
            "onset_date": "2025-06-01",
        },
    )
    assert resp.status_code == 201, resp.text
    condition = resp.json()
    assert condition["status"] == "chronic"
    assert condition["record_count"] == 0 and condition["medication_count"] == 0

    # transition to resolved without a date → 422 (router-level invariant)
    resp = await c.patch(
        f"/api/v1/members/{member['id']}/conditions/{condition['id']}",
        json={"status": "resolved"},
    )
    assert resp.status_code == 422

    # update that would put resolution before onset → 422
    resp = await c.patch(
        f"/api/v1/members/{member['id']}/conditions/{condition['id']}",
        json={"resolution_date": "2025-01-01"},
    )
    assert resp.status_code == 422

    # legitimate resolution
    resp = await c.patch(
        f"/api/v1/members/{member['id']}/conditions/{condition['id']}",
        json={"status": "resolved", "resolution_date": "2026-02-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert resp.json()["resolution_date"] == "2026-02-01"


@pytest.mark.asyncio
async def test_condition_record_medication_linking(auth_api):
    c = auth_api
    member = await _member(c)
    cond = (
        await c.post(
            f"/api/v1/members/{member['id']}/conditions",
            json={"name": "Asthma", "onset_date": "2026-01-01"},
        )
    ).json()

    record = (
        await c.post(
            f"/api/v1/members/{member['id']}/records",
            json={"record_type": "doctor_visit", "record_date": "2026-01-15", "summary": "wheeze"},
        )
    ).json()
    med = await _medication(c, member["id"], "Salbutamol", start_date="2026-01-15")

    base = f"/api/v1/members/{member['id']}/conditions/{cond['id']}"
    assert (await c.post(f"{base}/records/{record['id']}")).status_code == 204
    # idempotent re-link
    assert (await c.post(f"{base}/records/{record['id']}")).status_code == 204
    assert (await c.post(f"{base}/medications/{med['id']}")).status_code == 204

    body = (await c.get(base)).json()
    assert body["record_count"] == 1
    assert body["medication_count"] == 1

    # unlinking a non-linked entity 404s
    other_record = (
        await c.post(
            f"/api/v1/members/{member['id']}/records",
            json={"record_date": "2026-01-20"},
        )
    ).json()
    assert (await c.delete(f"{base}/records/{other_record['id']}")).status_code == 404

    assert (await c.delete(f"{base}/records/{record['id']}")).status_code == 204
    body = (await c.get(base)).json()
    assert body["record_count"] == 0

    # deleting the episode leaves the linked medication intact
    assert (await c.delete(base)).status_code == 204
    meds = (await c.get(f"/api/v1/members/{member['id']}/medications")).json()
    assert [m["id"] for m in meds] == [med["id"]]


# ── allergies ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_allergy_crud(auth_api):
    c = auth_api
    member = await _member(c)
    allergy = await _allergy(
        c, member["id"], "Peanuts", severity="severe", reaction="anaphylaxis", verified=False
    )
    assert allergy["severity"] == "severe"

    patched = await c.patch(
        f"/api/v1/members/{member['id']}/allergies/{allergy['id']}",
        json={"verified": True},
    )
    assert patched.json()["verified"] is True

    listed = (await c.get(f"/api/v1/members/{member['id']}/allergies")).json()
    assert [a["substance"] for a in listed] == ["Peanuts"]

    assert (
        await c.delete(f"/api/v1/members/{member['id']}/allergies/{allergy['id']}")
    ).status_code == 204
    assert (await c.get(f"/api/v1/members/{member['id']}/allergies")).json() == []


@pytest.mark.asyncio
async def test_allergy_conflict_matching(auth_api):
    c = auth_api
    member = await _member(c)
    url = f"/api/v1/members/{member['id']}/allergy-conflicts"

    # Cross-class: "penicillin" allergy vs "Amoxicillin" — name match only,
    # so this must NOT fire.
    await _allergy(c, member["id"], "penicillin", severity="moderate")
    amox = await _medication(c, member["id"], "Amoxicillin", start_date="2026-01-01")
    assert (await c.get(url)).json() == []

    # Exact normalized-name match fires ("aspirin" ⊂ "aspirin500").
    await _allergy(c, member["id"], "aspirin", severity="severe")
    await _medication(c, member["id"], "Aspirin 500", start_date="2026-01-01")
    conflicts = (await c.get(url)).json()
    assert len(conflicts) == 1
    hit = conflicts[0]
    assert hit["allergy"] == "aspirin"
    assert hit["medication"] == "Aspirin 500"
    assert hit["matched_on"] == "medicine_name"
    assert hit["severity"] == "severe"

    # Very short substances match exactly only — "as" must not fire in Aspirin.
    await _allergy(c, member["id"], "as")
    conflicts = (await c.get(url)).json()
    assert all(hit["allergy"] != "as" for hit in conflicts)

    # Stopped medications don't conflict.
    await c.patch(
        f"/api/v1/members/{member['id']}/medications/{amox['id']}",
        json={"status": "stopped"},
    )
    # amox wasn't matching anyway; stop the aspirin too and the list empties.
    meds = (
        await c.get(f"/api/v1/members/{member['id']}/medications", params={"status": "active"})
    ).json()
    for m in meds:
        await c.patch(
            f"/api/v1/members/{member['id']}/medications/{m['id']}",
            json={"status": "stopped"},
        )
    assert (await c.get(url)).json() == []


# ── symptoms ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_symptom_crud_and_correlations(auth_api):
    c = auth_api
    member = await _member(c)

    fever = (
        await c.post(
            f"/api/v1/members/{member['id']}/symptoms",
            json={"symptom": "Fever", "severity": "moderate", "started_at": "2026-01-10"},
        )
    ).json()
    assert fever["symptom"] == "fever"  # normalized to lowercase key

    await c.post(
        f"/api/v1/members/{member['id']}/symptoms",
        json={"symptom": "headache", "severity": "mild", "started_at": "2026-01-11"},
    )

    # resolved before onset → 422
    resp = await c.patch(
        f"/api/v1/members/{member['id']}/symptoms/{fever['id']}",
        json={"resolved_at": "2026-01-01"},
    )
    assert resp.status_code == 422

    resp = await c.patch(
        f"/api/v1/members/{member['id']}/symptoms/{fever['id']}",
        json={"resolved_at": "2026-01-12"},
    )
    assert resp.json()["resolved_at"] == "2026-01-12"

    # fixtures for the correlation view
    await _medication(c, member["id"], "Ibuprofen", start_date="2026-01-01", duration_days=30)
    resp = await c.post(
        f"/api/v1/members/{member['id']}/labs",
        json={"test_name": "CBC", "record_date": "2026-01-12", "flag": "high"},
    )
    assert resp.status_code == 201, resp.text

    corr = (
        await c.get(
            f"/api/v1/members/{member['id']}/symptoms/correlations",
            params={"symptom": "fever"},
        )
    ).json()
    assert corr["symptom"] == "fever"
    assert corr["occurrences"] == 1
    assert corr["severity_counts"] == {"mild": 0, "moderate": 1, "severe": 0}
    assert corr["with_medications"][0]["name"] == "Ibuprofen"
    assert corr["with_medications"][0]["count"] == 1
    assert corr["with_abnormal_labs"][0]["name"] == "CBC"
    assert corr["co_occurring_symptoms"][0]["name"] == "headache"
    assert "not causation" in corr["disclaimer"]

    # filter + 404 on unknown symptom
    listed = (
        await c.get(f"/api/v1/members/{member['id']}/symptoms", params={"symptom": "headache"})
    ).json()
    assert [s["symptom"] for s in listed] == ["headache"]
    resp = await c.get(
        f"/api/v1/members/{member['id']}/symptoms/correlations",
        params={"symptom": "rash"},
    )
    assert resp.status_code == 404

    assert (
        await c.delete(f"/api/v1/members/{member['id']}/symptoms/{fever['id']}")
    ).status_code == 204


# ── vaccinations ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vaccination_crud(auth_api):
    c = auth_api
    member = await _member(c)
    url = f"/api/v1/members/{member['id']}/vaccinations"

    vax = (
        await c.post(
            url,
            json={"name": "BCG", "date_administered": "2025-06-01", "notes": "right arm"},
        )
    ).json()
    assert vax["name"] == "BCG"

    patched = await c.patch(f"{url}/{vax['id']}", json={"booster_due_date": "2030-06-01"})
    assert patched.json()["booster_due_date"] == "2030-06-01"

    listed = (await c.get(url)).json()
    assert [v["name"] for v in listed] == ["BCG"]

    assert (await c.delete(f"{url}/{vax['id']}")).status_code == 204
    assert (await c.get(url)).json() == []


# ── immunization schedule + milestones ────────────────────────────────


@pytest.mark.asyncio
async def test_immunization_schedule(auth_api):
    c = auth_api
    member = await _member(c, "Baby", birth_date="2025-06-01")
    url = f"/api/v1/members/{member['id']}/immunizations/schedule"

    # birth-date required
    other = await _member(c, "NoDob")
    assert (await c.get(f"/api/v1/members/{other['id']}/immunizations/schedule")).status_code == 422

    schedule = (await c.get(url)).json()
    assert schedule["summary"]["total"] == len(schedule["doses"]) > 0
    # Nothing given, child is ~17 months: some doses complete-by-default
    # (birth doses are not auto-complete — they must be overdue).
    assert any(d["status"] == "overdue" for d in schedule["doses"])

    # Log the BCG and the birth hep-B → both doses complete.
    for name in ("BCG", "Hepatitis B birth"):
        assert (
            await c.post(
                f"/api/v1/members/{member['id']}/vaccinations",
                json={"name": name, "date_administered": "2025-06-01"},
            )
        ).status_code == 201

    schedule = (await c.get(url)).json()
    by_label = {d["label"]: d for d in schedule["doses"]}
    assert by_label["BCG"]["status"] == "complete"
    assert by_label["BCG"]["given_date"] == "2025-06-01"
    assert by_label["Hep-B birth"]["status"] == "complete"
    assert schedule["summary"]["complete"] >= 2


@pytest.mark.asyncio
async def test_milestones_set_and_clear(auth_api):
    c = auth_api
    member = await _member(c, "Toddler", birth_date="2024-06-01")
    url = f"/api/v1/members/{member['id']}/milestones"

    listing = (await c.get(url)).json()
    assert listing["age_months"] is not None and listing["age_months"] > 20
    keys = {row["key"] for row in listing["rows"]}
    assert {"social_smile", "walks", "hops"} <= keys
    assert all(row["achieved"] is False for row in listing["rows"])
    # A 2-year-old: walking expected, hopping not yet.
    by_key = {row["key"]: row for row in listing["rows"]}
    assert by_key["walks"]["expected"] == "achieved"
    assert by_key["hops"]["expected"] == "upcoming"

    # unknown milestone
    resp = await c.put(f"{url}/not_a_milestone", json={"achieved": True})
    assert resp.status_code == 404

    resp = await c.put(f"{url}/walks", json={"achieved": True, "achieved_on": "2025-06-15"})
    assert resp.json() == {"key": "walks", "achieved": True}

    listing = (await c.get(url)).json()
    walks = next(r for r in listing["rows"] if r["key"] == "walks")
    assert walks["achieved"] is True and walks["achieved_on"] == "2025-06-15"

    # clearing
    resp = await c.put(f"{url}/walks", json={"achieved": False})
    assert resp.json()["achieved"] is False
    listing = (await c.get(url)).json()
    assert all(row["achieved"] is False for row in listing["rows"])


# ── growth report ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_growth_report_percentiles(auth_api):
    c = auth_api
    birth = date(date.today().year - 2, date.today().month, 1)  # ~24-35 months old
    member = await _member(c, "Grower", birth_date=birth.isoformat())

    reading_day = date.today()
    await _vital(c, member["id"], "weight", 13.0, reading_day)
    await _vital(c, member["id"], "height", 89.0, reading_day)

    resp = await c.get(f"/api/v1/members/{member['id']}/growth/report", params={"sex": "male"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["age_months"] is not None and body["age_months"] > 23
    measures = {row["measure"]: row for row in body["rows"]}
    assert {"weight", "stature", "bmi"} <= set(measures)

    for measure in ("weight", "stature", "bmi"):
        row = measures[measure]
        assert 0.0 < row["percentile"] <= 99.9
        assert row["implausible"] is False
        assert abs(row["z"]) <= 5.0
        assert "lms" in row and all(k in row["lms"] for k in ("l", "m", "s"))

    bmi_value = measures["bmi"]["value"]
    assert bmi_value == pytest.approx(13.0 / (0.89**2), abs=0.1)

    # sex override changes the reference table (girl at same measurements →
    # still sane percentiles, different median).
    resp = await c.get(f"/api/v1/members/{member['id']}/growth/report", params={"sex": "female"})
    female_rows = {r["measure"]: r for r in resp.json()["rows"]}
    assert female_rows["weight"]["percentile"] != measures["weight"]["percentile"]

    # members without a birth date get an empty, explained report
    no_dob = await _member(c, "NoDob")
    resp = await c.get(f"/api/v1/members/{no_dob['id']}/growth/report")
    assert resp.json()["rows"] == []
    assert "birth" in resp.json()["note"]


@pytest.mark.asyncio
async def test_growth_report_skips_out_of_range_readings(auth_api):
    c = auth_api
    birth = date(date.today().year - 25, date.today().month, 1)  # 25 years old
    member = await _member(c, "Adult", birth_date=birth.isoformat())
    await _vital(c, member["id"], "weight", 70.0, date.today())

    body = (await c.get(f"/api/v1/members/{member['id']}/growth/report")).json()
    assert body["rows"] == []
    assert "240 months" in body["note"]
