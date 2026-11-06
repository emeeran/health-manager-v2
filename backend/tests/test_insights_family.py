"""Insight family: report kinds, standalone insights, alerts, grounding.

AI is patched at module scope (FakeProvider + build_plan patch) — tests
never reach a real provider.
"""

import json
import uuid

import pytest
import pytest_asyncio

from app.services.ai import router as ai_router
from app.services.insight_service import (
    GROUNDING_INVARIANT,
    metadata_only_citations,
)
from tests.test_thumbnails import make_png_bytes

QA_REPLY = json.dumps(
    {
        "headline": "HbA1c 8.4% is above target.",
        "narrative": "The recorded HbA1c of 8.4% on 2026-05-01 is above the "
        "usual target; discuss with your doctor.",
        "key_findings": ["HbA1c 8.4% on 2026-05-01"],
        "recommendations": ["Ask your doctor about the HbA1c trend."],
    }
)

FLAGGED_LAB_EXTRACTION = json.dumps(
    {
        "record_date": "2026-05-01",
        "doctor_name": "Dr. Fake",
        "diagnosis": "Type 2 Diabetes Mellitus",
        "summary": "Lab panel.",
        "medications": [],
        "labs": [
            {
                "name": "Hemoglobin",
                "result": "8.9",
                "units": "g/dL",
                "reference": "13.0-17.0",
                "flag": "low",
            }
        ],
        "vitals": [],
    }
)


class FakeProvider:
    def __init__(self, name: str = "fake", reply: str | None = None) -> None:
        self.name = name
        self.model = "fake-model"
        self.local = name.startswith("local")
        self.timeout = 5
        self.reply = reply
        self.calls: list[dict] = []

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.reply or "Deterministic narrative from the ground-truth snapshot."


@pytest.fixture
def patch_plan(monkeypatch):
    """Patch build_plan to return the given providers, capturing args."""

    def _patch(providers: list) -> dict:
        captured: dict[str, bool] = {}

        def fake_build(local_only: bool = False):
            captured["local_only"] = local_only
            return providers

        monkeypatch.setattr(ai_router, "build_plan", fake_build)
        return captured

    return _patch


@pytest_asyncio.fixture
async def insight_client(auth_client):
    """Register the insight-family routers (orchestrator wires main.py)."""
    from app.main import app
    from app.routers import ai_insights, health_alerts

    paths = {getattr(r, "path", "") for r in app.routes}
    if "/api/v1/insights" not in paths:
        app.include_router(ai_insights.router, prefix="/api/v1")
        app.include_router(health_alerts.router, prefix="/api/v1")
    return auth_client


async def _member(client, consent: bool = True) -> str:
    resp = await client.post("/api/v1/members", json={"name": "Asha", "cloud_ai_consent": consent})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _seed_meds_labs(client, member_id: str) -> None:
    """Two active meds + one flagged lab + one high BP reading."""
    for med in (
        {"medicine": "Metformin", "dosage": "500 mg", "timing": "after food"},
        {"medicine": "Met XL 25mg", "dosage": "25 mg", "timing": "morning"},
    ):
        resp = await client.post(f"/api/v1/members/{member_id}/medications", json=med)
        assert resp.status_code == 201, resp.text
    resp = await client.post(
        f"/api/v1/members/{member_id}/labs",
        json={
            "test_name": "HbA1c",
            "result": "8.4",
            "units": "%",
            "value_num": 8.4,
            "ref_low_num": 4.0,
            "ref_high_num": 5.6,
            "flag": "high",
            "record_date": "2026-05-01",
        },
    )
    assert resp.status_code == 201, resp.text


async def _read_sse(client, method: str, url: str, **kwargs) -> list[dict]:
    events: list[dict] = []
    async with client.stream(method, url, **kwargs) as resp:
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


# ── Report family: every kind generates, persists, latest round-trips ────────

KIND_SLUGS = [
    ("smart_report", "smart_report"),
    ("health_insights", "health_insights"),
    ("health_insights", "health-insights"),
    ("pre_consultation", "pre_consultation"),
    ("consultant_note", "consultant_note"),
    ("consolidated_report", "consolidated_report"),
    ("medication_report", "medication_report"),
    ("medication_schedule", "medication_schedule"),
    ("forecast", "forecast"),
]


@pytest.mark.parametrize(("kind", "slug"), KIND_SLUGS)
async def test_report_kind_roundtrip(insight_client, patch_plan, kind, slug):
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)

    events = await _read_sse(
        insight_client, "POST", f"/api/v1/members/{member_id}/reports/{slug}/stream"
    )
    assert events[-1]["stage"] == "complete", events
    stages = [e["stage"] for e in events]
    assert stages[0] == "stats"
    assert "narrating" in stages
    report = events[-1]["report"]
    assert report["kind"] == kind
    assert report["provider_used"] == "fake"

    # The prompt carried the DB-derived ground truth: the two active meds
    # appear in every kind; the flagged lab wherever the snapshot includes labs.
    prompt = provider.calls[0]["prompt"]
    assert "Metformin" in prompt
    assert "Met XL 25mg" in prompt
    if kind not in ("medication_report", "medication_schedule", "forecast"):
        assert "HbA1c" in prompt and "8.4" in prompt

    latest = await insight_client.get(
        f"/api/v1/members/{member_id}/reports/latest",
        params={"kind": kind},
    )
    assert latest.status_code == 200, latest.text
    body = latest.json()
    assert body["id"] == report["id"]
    assert body["content"] == report["content"]
    assert body["kind"] == kind


async def test_health_insights_grounds_full_history(insight_client, patch_plan):
    """Health Insights pulls family history, allergies, visits, both regimens,
    lab trends and vaccinations into the prompt and the saved sources."""
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _member(insight_client)

    patched = await insight_client.patch(
        f"/api/v1/members/{member_id}",
        json={
            "birth_date": "1974-03-02",
            "blood_group": "B+",
            "medical_history": "Asthma since childhood; appendectomy 2015",
            "family_medical_history": "Type 2 diabetes (mother), hypertension (father)",
            "emergency_contact_name": "Ravi",
            "emergency_contact_phone": "+91 90000 00000",
        },
    )
    assert patched.status_code == 200, patched.text

    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/allergies",
        json={
            "substance": "Penicillin",
            "severity": "severe",
            "reaction": "Anaphylaxis",
            "verified": True,
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/conditions",
        json={
            "name": "Type 2 Diabetes Mellitus",
            "icd10_code": "E11",
            "status": "chronic",
            "onset_date": "2021-06-01",
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-04-10",
            "doctor_name": "Dr. Rao",
            "diagnosis": "Poor glycemic control",
            "investigations": "HbA1c, lipid profile",
            "summary": "Discussed diet and adherence.",
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/vaccinations",
        json={"name": "Influenza", "date_administered": "2025-11-01"},
    )
    assert resp.status_code == 201, resp.text

    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/vitals",
        json={
            "vital_type": "blood_pressure",
            "value_num": 152,
            "value_secondary": 96,
            "unit": "mmHg",
            "measured_at": "2026-04-10T09:00:00Z",
        },
    )
    assert resp.status_code == 201, resp.text

    active = await insight_client.post(
        f"/api/v1/members/{member_id}/medications",
        json={
            "medicine": "Metformin",
            "dosage": "500 mg",
            "timing": "after food",
            "start_date": "2021-06-02",
            "provider_name": "Dr. Rao",
        },
    )
    assert active.status_code == 201, active.text
    past = await insight_client.post(
        f"/api/v1/members/{member_id}/medications",
        json={"medicine": "Glibenclamide", "dosage": "5 mg"},
    )
    assert past.status_code == 201, past.text
    stopped = await insight_client.patch(
        f"/api/v1/members/{member_id}/medications/{past.json()['id']}",
        json={"status": "stopped", "end_date": "2022-01-15"},
    )
    assert stopped.status_code == 200, stopped.text

    for value, day in ((8.0, "2026-01-01"), (8.4, "2026-05-01")):
        resp = await insight_client.post(
            f"/api/v1/members/{member_id}/labs",
            json={
                "test_name": "HbA1c",
                "result": str(value),
                "units": "%",
                "value_num": value,
                "ref_low_num": 4.0,
                "ref_high_num": 5.6,
                "flag": "high",
                "record_date": day,
            },
        )
        assert resp.status_code == 201, resp.text

    events = await _read_sse(
        insight_client,
        "POST",
        f"/api/v1/members/{member_id}/reports/health-insights/stream",
    )
    assert events[-1]["stage"] == "complete", events
    report = events[-1]["report"]
    assert report["kind"] == "health_insights"

    prompt = provider.calls[0]["prompt"]
    assert "Type 2 diabetes (mother), hypertension (father)" in prompt
    assert "Asthma since childhood" in prompt
    assert "Penicillin" in prompt and "Anaphylaxis" in prompt
    assert "Type 2 Diabetes Mellitus" in prompt and "E11" in prompt
    assert "Dr. Rao" in prompt and "Poor glycemic control" in prompt
    assert "Metformin" in prompt
    assert "Glibenclamide" in prompt
    assert "Influenza" in prompt
    assert "4-5.6" in prompt  # reference range, rendered in code
    assert '"previous"' in prompt and '"delta_num": 0.4' in prompt

    sources = report["sources"]
    assert sources["family_medical_history"].startswith("Type 2 diabetes")
    assert sources["allergies"][0]["substance"] == "Penicillin"
    assert sources["conditions"][0]["icd10_code"] == "E11"
    assert sources["doctor_visits"][0]["diagnosis"] == "Poor glycemic control"
    assert sources["medications_active"][0]["medicine"] == "Metformin"
    assert sources["medications_past"][0]["medicine"] == "Glibenclamide"
    assert sources["vitals_latest"][0]["vital_type"] == "blood_pressure"
    assert sources["lab_trends"]["HbA1c"]["previous"]["value_num"] == 8.0
    assert sources["lab_trends"]["HbA1c"]["delta_num"] == 0.4
    assert report["verification_id"] is not None


async def test_latest_rejects_unknown_kind(insight_client, patch_plan):
    patch_plan([FakeProvider()])
    member_id = await _member(insight_client)
    resp = await insight_client.get(
        f"/api/v1/members/{member_id}/reports/latest", params={"kind": "nope"}
    )
    assert resp.status_code == 422


async def test_report_snapshot_context_medication_schedule(insight_client, patch_plan):
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)
    await _read_sse(
        insight_client,
        "POST",
        f"/api/v1/members/{member_id}/reports/medication-schedule/stream",
    )
    # Slot grouping is computed in code (dosing.expand_day defaults).
    prompt = provider.calls[0]["prompt"]
    assert '"slots"' in prompt
    assert "Metformin" in prompt


async def test_forecast_projection_computed_in_code(insight_client, patch_plan):
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _member(insight_client)
    for value, day in ((8.0, "2026-01-01"), (8.2, "2026-02-01"), (8.4, "2026-03-01")):
        resp = await insight_client.post(
            f"/api/v1/members/{member_id}/labs",
            json={
                "test_name": "HbA1c",
                "result": str(value),
                "value_num": value,
                "flag": "high",
                "record_date": day,
            },
        )
        assert resp.status_code == 201, resp.text
    await _read_sse(insight_client, "POST", f"/api/v1/members/{member_id}/reports/forecast/stream")
    # The regression numbers come from code, in the prompt AND the snapshot.
    prompt = provider.calls[0]["prompt"]
    assert "lab:HbA1c" in prompt
    assert "slope_per_day" in prompt
    latest = (
        await insight_client.get(
            f"/api/v1/members/{member_id}/reports/latest", params={"kind": "forecast"}
        )
    ).json()
    projection = latest["sources"]["projections"]["lab:HbA1c"]
    assert projection["sufficient_data"] is True
    assert projection["n"] == 3
    assert projection["slope_per_day"] > 0
    assert projection["projected_next"] > projection["latest_value"]


async def test_report_stream_respects_cloud_consent(insight_client, patch_plan):
    provider = FakeProvider(name="local-ollama")
    captured = patch_plan([provider])
    member_id = await _member(insight_client, consent=False)
    await _read_sse(insight_client, "POST", f"/api/v1/members/{member_id}/reports/smart/stream")
    assert captured["local_only"] is True


# ── Standalone insights ──────────────────────────────────────────────────────


async def test_health_qa_json_insight(insight_client, patch_plan):
    provider = FakeProvider(reply=QA_REPLY)
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)

    resp = await insight_client.post(
        "/api/v1/insights",
        json={
            "member_id": member_id,
            "kind": "health_qa",
            "question": "Is my sugar under control?",
            "stream": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "health_qa"
    payload = json.loads(body["content"])
    assert payload["headline"].startswith("HbA1c 8.4%")
    assert body["sources"]["structured_ok"] is True
    # Ground-truth stats are persisted with the insight, citations metadata-only.
    assert body["sources"]["ground_truth_stats"]["medications_count"] == 2
    assert body["sources"]["citations"] == []

    listing = await insight_client.get(
        "/api/v1/insights", params={"member_id": member_id, "kind": "health_qa"}
    )
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [body["id"]]

    single = await insight_client.get(f"/api/v1/insights/{body['id']}")
    assert single.status_code == 200
    assert single.json()["id"] == body["id"]


async def test_health_qa_stream_and_other_kind(insight_client, patch_plan):
    provider = FakeProvider(reply=QA_REPLY)
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)
    events = await _read_sse(
        insight_client,
        "POST",
        "/api/v1/insights",
        json={"member_id": member_id, "kind": "health_qa", "question": "why?"},
    )
    assert events[-1]["stage"] == "complete"
    assert json.loads(events[-1]["report"]["content"])["headline"]

    # Any report kind is also reachable through POST /insights.
    provider_reply = FakeProvider()
    patch_plan([provider_reply])
    events = await _read_sse(
        insight_client,
        "POST",
        "/api/v1/insights",
        json={"member_id": member_id, "kind": "consultant_note"},
    )
    assert events[-1]["report"]["kind"] == "consultant_note"


async def test_health_qa_requires_question(insight_client, patch_plan):
    patch_plan([FakeProvider()])
    member_id = await _member(insight_client)
    resp = await insight_client.post(
        "/api/v1/insights",
        json={"member_id": member_id, "kind": "health_qa", "stream": False},
    )
    assert resp.status_code == 422


async def test_health_qa_cloud_consent_local_only(insight_client, patch_plan):
    provider = FakeProvider(name="local-ollama", reply=QA_REPLY)
    captured = patch_plan([provider])
    member_id = await _member(insight_client, consent=False)
    await insight_client.post(
        "/api/v1/insights",
        json={
            "member_id": member_id,
            "kind": "health_qa",
            "question": "q",
            "stream": False,
        },
    )
    assert captured["local_only"] is True


async def test_insight_read_unknown_id_404(insight_client):
    resp = await insight_client.get(f"/api/v1/insights/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Health alerts ────────────────────────────────────────────────────────────


async def test_flagged_lab_extraction_creates_alert(insight_client, patch_plan):
    provider = FakeProvider(reply=FLAGGED_LAB_EXTRACTION)
    patch_plan([provider])
    member_id = await _member(insight_client)
    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("lab.png", make_png_bytes(), "image/png"))],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["health_alerts_created"] == 1

    alerts = (await insight_client.get(f"/api/v1/members/{member_id}/health-alerts")).json()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["alert_type"] == "lab_anomaly"
    assert alert["title"] == "Hemoglobin low"
    assert "8.9" in alert["message"]
    assert alert["acknowledged"] is False

    # Re-extracting the same report must not stack duplicates.
    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("lab.png", make_png_bytes(), "image/png"))],
    )
    assert resp.json()["health_alerts_created"] == 0

    ack = await insight_client.post(
        f"/api/v1/members/{member_id}/health-alerts/{alert['id']}/acknowledge"
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["acknowledged"] is True

    open_alerts = (
        await insight_client.get(
            f"/api/v1/members/{member_id}/health-alerts",
            params={"unacknowledged_only": True},
        )
    ).json()
    assert open_alerts == []


async def test_critical_lab_severity(insight_client, patch_plan):
    critical = json.loads(FLAGGED_LAB_EXTRACTION)
    critical["labs"] = [
        {
            "name": "Hemoglobin",
            "result": "3.0",
            "units": "g/dL",
            "reference": "13.0-17.0",
            "value_num": 3.0,
            "ref_low_num": 13.0,
            "ref_high_num": 17.0,
            "flag": "low",
        }
    ]
    provider = FakeProvider(reply=json.dumps(critical))
    patch_plan([provider])
    member_id = await _member(insight_client)
    await insight_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("lab.png", make_png_bytes(), "image/png"))],
    )
    alerts = (await insight_client.get(f"/api/v1/members/{member_id}/health-alerts")).json()
    assert alerts[0]["severity"] == "critical"


async def test_normal_lab_creates_no_alert(insight_client, patch_plan):
    reply = json.loads(FLAGGED_LAB_EXTRACTION)
    reply["labs"][0]["flag"] = "normal"
    provider = FakeProvider(reply=json.dumps(reply))
    patch_plan([provider])
    member_id = await _member(insight_client)
    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("lab.png", make_png_bytes(), "image/png"))],
    )
    assert resp.json()["health_alerts_created"] == 0
    assert (await insight_client.get(f"/api/v1/members/{member_id}/health-alerts")).json() == []


async def test_alerts_require_scoped_member(insight_client):
    resp = await insight_client.get(f"/api/v1/members/{uuid.uuid4()}/health-alerts")
    assert resp.status_code == 404


# ── Reference ranges with citations ──────────────────────────────────────────


async def test_reference_ranges_carry_citations(auth_client):
    resp = await auth_client.get("/api/v1/reference-ranges")
    assert resp.status_code == 200
    body = resp.json()
    for band in body["blood_pressure"]["bands"]:
        source = band["source"]
        assert source["org"] and source["document"] and source["url"]
        assert source["url"].startswith("http")
    assert body["labs"]["hba1c"]["source"]["url"]
    assert body["labs"]["ldl_cholesterol"]["source"]["year"]

    filtered = await auth_client.get("/api/v1/reference-ranges", params={"type": "labs"})
    assert set(filtered.json().keys()) == {"labs"}

    missing = await auth_client.get("/api/v1/reference-ranges", params={"type": "nope"})
    assert missing.status_code == 404


async def test_bp_stage_includes_citation(auth_client):
    resp = await auth_client.get(
        "/api/v1/reference-ranges/bp-stage", params={"systolic": 150, "diastolic": 95}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "High BP (Stage 2)"
    assert body["source"]["org"].startswith("American College")


# ── Grounding invariant ──────────────────────────────────────────────────────


def test_metadata_only_citations_strips_excerpts():
    citations = [
        {
            "source": "harrison's.pdf",
            "page": 42,
            "text": "EXCERPT TEXT MUST NOT LEAK",
            "snippet": "EXCERPT SNIPPET MUST NOT LEAK",
        }
    ]
    cleaned = metadata_only_citations(citations)
    assert cleaned == [{"source": "harrison's.pdf", "page": 42}]
    assert "EXCERPT" not in json.dumps(cleaned)


def test_grounding_invariant_declared():
    assert "METADATA ONLY" in GROUNDING_INVARIANT


async def test_qa_grounding_citations_metadata_only(monkeypatch):
    """Even when an index grounds the answer, citations expose metadata only."""
    from app.services import insight_service, rag

    def fake_rag_grounding(query: str):
        return (
            "Reference excerpts (prompt-only, never returned):\n[1] LEAK?",
            [
                {"source": "ref.pdf", "page": 7, "text": "LEAK?"},
                {"source": "ref.pdf", "page": 9, "snippet": "LEAK?"},
            ],
        )

    monkeypatch.setattr(rag, "grounding_block", fake_rag_grounding)
    block, citations = insight_service.grounded_reference_block("q")
    assert "LEAK?" in block  # excerpt stays in the prompt block
    assert citations == [
        {"source": "ref.pdf", "page": 7},
        {"source": "ref.pdf", "page": 9},
    ]


async def test_report_stream_schedules_claim_audit(insight_client, patch_plan, monkeypatch):
    """The report stream hands the narrative (not the prompt) to the audit."""
    from app.services.ai import verification as verification_service

    captured: dict = {}

    async def fake_schedule(db, member_id, subject_type, narrative, verifier, **kwargs):
        captured.update(
            member_id=member_id,
            subject_type=subject_type,
            narrative=narrative,
            verifier=verifier,
            **kwargs,
        )
        return uuid.uuid4()

    monkeypatch.setattr(verification_service, "schedule_audit", fake_schedule)
    patch_plan([FakeProvider()])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)

    events = await _read_sse(
        insight_client,
        "POST",
        f"/api/v1/members/{member_id}/reports/health-insights/stream",
    )

    assert events[-1]["stage"] == "complete"
    assert captured["subject_type"] == "report:health_insights"
    assert captured["kind"] == "health_insights"
    assert captured["narrative"] == "Deterministic narrative from the ground-truth snapshot."


async def test_health_qa_schedules_audit_with_readable_prose(
    insight_client, patch_plan, monkeypatch
):
    from app.services.ai import verification as verification_service

    captured: dict = {}

    async def fake_schedule(db, member_id, subject_type, narrative, verifier, **kwargs):
        captured.update(subject_type=subject_type, narrative=narrative, **kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(verification_service, "schedule_audit", fake_schedule)
    patch_plan([FakeProvider(reply=QA_REPLY)])
    member_id = await _member(insight_client)

    resp = await insight_client.post(
        "/api/v1/insights",
        json={
            "member_id": member_id,
            "kind": "health_qa",
            "question": "How is the HbA1c?",
            "stream": False,
        },
    )

    assert resp.status_code == 200, resp.text
    assert captured["subject_type"] == "insight:health_qa"
    assert "HbA1c 8.4% is above target." in captured["narrative"]
    assert "key_findings" not in captured["narrative"]
