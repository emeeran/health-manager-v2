"""Cross-member search (FTS5 mirror) + household dashboard.

Importing SearchMirror at module scope registers the model on Base
metadata before conftest's create_all runs (the orchestrator owns
app/models/__init__.py and app/main.py wiring, so the tests mount the
routers themselves, idempotently).
"""

import uuid
from datetime import date, timedelta

import pytest_asyncio

from app.models.search_mirror import SearchMirror  # noqa: F401


def _ensure_router(app, router, prefix: str = "/api/v1") -> None:
    """Mount a router once (idempotent if the orchestrator already did)."""
    existing = {getattr(r, "path", None) for r in app.routes}
    if not all(prefix + route.path in existing for route in router.routes):
        app.include_router(router, prefix=prefix)


def _mount(client):
    from app.main import app
    from app.routers import dashboard, search

    _ensure_router(app, search.router)
    _ensure_router(app, dashboard.router)
    return client


@pytest_asyncio.fixture
def api(auth_client):
    return _mount(auth_client)


@pytest_asyncio.fixture
def bare_api(client):
    """Routers mounted, but no auth cookie."""
    return _mount(client)


# ── helpers ───────────────────────────────────────────────────────────


async def _create_member(client, name: str) -> dict:
    resp = await client.post("/api/v1/members", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_record(client, member_id: str, **fields) -> dict:
    payload = {"record_type": "doctor_visit", "record_date": "2026-05-01", **fields}
    resp = await client.post(f"/api/v1/members/{member_id}/records", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _reindex(client) -> int:
    resp = await client.post("/api/v1/search/reindex")
    assert resp.status_code == 200, resp.text
    return resp.json()["indexed"]


async def _search(client, q: str, **params) -> list[dict]:
    resp = await client.get("/api/v1/search", params={"q": q, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── search ────────────────────────────────────────────────────────────


async def test_search_requires_auth(bare_api):
    resp = await bare_api.get("/api/v1/search", params={"q": "diabetes"})
    assert resp.status_code == 401


async def test_reindex_and_cross_member_hits(api):
    asha = await _create_member(api, "Asha")
    rahul = await _create_member(api, "Rahul")

    await _create_record(
        api, asha["id"], diagnosis="Type 2 Diabetes follow-up", summary="A1c stable"
    )
    resp = await api.post(
        f"/api/v1/members/{rahul['id']}/medications",
        json={"medicine": "Metformin", "dosage": "500 mg"},
    )
    assert resp.status_code == 201, resp.text
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/labs",
        json={"test_name": "HbA1c", "result": "6.8", "units": "%", "flag": "high"},
    )
    assert resp.status_code == 201, resp.text

    indexed = await _reindex(api)
    assert indexed == 3

    hits = await _search(api, "diabetes")
    assert len(hits) == 1
    hit = hits[0]
    assert hit["row_type"] == "record"
    assert hit["member_name"] == "Asha"
    assert hit["member_id"] == asha["id"]
    assert "Diabetes" in hit["snippet"]
    assert hit["score"] > 0

    hits = await _search(api, "metformin")
    assert [h["row_type"] for h in hits] == ["medication"]
    assert hits[0]["member_name"] == "Rahul"

    hits = await _search(api, "hba1c")
    assert [h["row_type"] for h in hits] == ["lab"]

    # member_id filter scopes results to one member.
    hits = await _search(api, "metformin", member_id=asha["id"])
    assert hits == []

    # Another member's vitals + symptom + condition + allergy also surface.
    resp = await api.post(
        f"/api/v1/members/{rahul['id']}/vitals",
        json={
            "vital_type": "blood_pressure",
            "value_num": 150,
            "value_secondary": 95,
            "measured_at": "2026-05-02T08:00:00",
        },
    )
    assert resp.status_code == 201, resp.text
    await _reindex(api)
    hits = await _search(api, "blood_pressure 150")
    assert hits and hits[0]["row_type"] == "vital"

    # FTS syntax in the query is defused, not interpreted.
    hits = await _search(api, "diabetes OR (metformin*) AND NOT a")
    assert hits == []


async def test_reindex_refreshes_stale_mirror(api):
    asha = await _create_member(api, "Asha")
    record = await _create_record(api, asha["id"], diagnosis="Migraine")
    await _reindex(api)
    assert await _search(api, "migraine")

    resp = await api.delete(f"/api/v1/members/{asha['id']}/records/{record['id']}")
    assert resp.status_code in (200, 204), resp.text
    # No per-write hook in this slice: stale until reindex (documented).
    assert await _search(api, "migraine")
    await _reindex(api)
    assert await _search(api, "migraine") == []


async def test_symptoms_are_mirrored(api, session_factory):
    asha = await _create_member(api, "Asha")
    from app.models import SymptomEntry

    async with session_factory() as session:
        session.add(
            SymptomEntry(
                member_id=uuid.UUID(asha["id"]),
                symptom="nausea",
                severity="moderate",
                started_at=date(2026, 4, 20),
            )
        )
        await session.commit()
    await _reindex(api)
    hits = await _search(api, "nausea")
    assert hits and hits[0]["row_type"] == "symptom"


# ── dashboard ─────────────────────────────────────────────────────────


async def test_dashboard_requires_auth(bare_api):
    resp = await bare_api.get("/api/v1/dashboard")
    assert resp.status_code == 401


async def test_dashboard_empty_household(api):
    resp = await api.get("/api/v1/dashboard")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["members"] == []
    assert body["scores"] == []
    assert body["alerts"] == []
    assert body["risk_summary"] == {
        "high_risk_members": 0,
        "moderate_risk_members": 0,
        "low_risk_members": 0,
    }
    assert body["vaccination_status"] == {"total_vaccinations": 0, "overdue_count": 0}


async def test_dashboard_scores_alerts_activity(api, session_factory):
    asha = await _create_member(api, "Asha")

    # Records: one doctor visit (recent) + one lab report, 40 days ago.
    today = date.today()
    await _create_record(
        api,
        asha["id"],
        record_type="doctor_visit",
        record_date=today.isoformat(),
        diagnosis="Diabetes review",
    )
    await _create_record(
        api,
        asha["id"],
        record_type="lab_report",
        record_date=(today - timedelta(days=40)).isoformat(),
    )
    # Vitals: height 170cm + weight 95kg → BMI ~32.9 (obese, penalised).
    for vital_type, value in (("height", 170), ("weight", 95)):
        resp = await api.post(
            f"/api/v1/members/{asha['id']}/vitals",
            json={
                "vital_type": vital_type,
                "value_num": value,
                "measured_at": f"{today.isoformat()}T08:00:00",
            },
        )
        assert resp.status_code == 201, resp.text
    # Abnormal lab → alert.
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/labs",
        json={
            "test_name": "HbA1c",
            "result": "9.1",
            "units": "%",
            "value_num": 9.1,
            "ref_low_num": 4.0,
            "ref_high_num": 5.6,
            "flag": "high",
        },
    )
    assert resp.status_code == 201, resp.text
    # Active medications: Metformin + Penicillin V, which conflicts with
    # the Penicillin allergy added below → alert.
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/medications",
        json={"medicine": "Metformin", "dosage": "500 mg"},
    )
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/medications",
        json={"medicine": "Penicillin V", "dosage": "500 mg"},
    )
    assert resp.status_code == 201, resp.text
    # Allergy conflicting with the active medication → alert.
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/allergies",
        json={"substance": "Penicillin", "severity": "severe"},
    )
    assert resp.status_code == 201, resp.text
    # Overdue booster → alert.
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/vaccinations",
        json={
            "name": "Tetanus",
            "date_administered": "2020-01-10",
            "booster_due_date": "2025-12-01",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    # Active condition episode → conditions_management penalty.
    resp = await api.post(
        f"/api/v1/members/{asha['id']}/conditions",
        json={"name": "Type 2 Diabetes", "status": "chronic"},
    )
    assert resp.status_code in (200, 201), resp.text

    resp = await api.get("/api/v1/dashboard")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Scores + strip.
    assert len(body["scores"]) == 1
    score = body["scores"][0]
    assert score["member_id"] == asha["id"]
    assert 0 <= score["health_score"] <= 100
    for category in (
        "bmi",
        "conditions_management",
        "lab_compliance",
        "medication_tracking",
        "profile_completeness",
        "record_recency",
    ):
        assert category in score["score_breakdown"]
    # Obese BMI scores below its max.
    assert score["score_breakdown"]["bmi"]["score"] < 20
    assert body["members"][0]["health_score"] == score["health_score"]

    # Alerts: abnormal lab, allergy conflict, overdue booster.
    alert_types = {a["alert_type"] for a in body["alerts"]}
    assert {
        "abnormal_lab",
        "allergy_conflict",
        "overdue_booster",
    } <= alert_types
    lab_alert = next(a for a in body["alerts"] if a["alert_type"] == "abnormal_lab")
    assert lab_alert["member_name"] == "Asha"
    assert lab_alert["severity"] == "high"  # 9.1 >= 1.5 * 5.6

    # Activity: records in the 30-day window + a cross-entity feed.
    assert body["record_activity"]["total_last_30_days"] == 1
    assert body["record_activity"]["by_type"].get("doctor_visit") == 1
    kinds = {item["kind"] for item in body["activity_feed"]}
    assert {"record", "lab", "vital"} <= kinds

    # Medication summary + vaccination status.
    assert body["medication_summary"]["total_active_medications"] == 2
    assert body["medication_summary"]["members_with_medications"] == 1
    assert body["vaccination_status"] == {"total_vaccinations": 1, "overdue_count": 1}

    # Risk summary reflects the computed score.
    assert sum(body["risk_summary"].values()) == 1
