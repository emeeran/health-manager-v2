"""AI-tools additions: visit_summary kind, structured pre_consultation A5
note, pair drug interactions, price comparison + catalog refresh.

AI is patched at module scope (FakeProvider + build_plan patch) — tests
never reach a real provider.
"""

import json
import uuid
from datetime import date
from types import SimpleNamespace

from app.services import local_drug_service
from tests.test_insights_family import (  # noqa: F401, F811 — pytest fixtures, injected by param name
    FakeProvider,
    _member,
    _read_sse,
    _seed_meds_labs,
    insight_client,
    patch_plan,
)

A5_REPLY = json.dumps(
    {
        "date": "2026-11-10",
        "member_name": "Asha",
        "chronic_conditions": ["Type 2 Diabetes Mellitus"],
        "chief_complaints": ["burning feet at night"],
        "to_discuss": [
            "HbA1c 8.4% above target",
            "Switch Met XL dose",
            "Diet review",
        ],
        "current_medications": ["Metformin 500 mg", "Met XL 25 mg"],
    }
)

PAIR_REPLY = json.dumps(
    [
        {
            "drugs": ["Met XL", "CardiCare"],
            "interaction": "Additive bradycardia risk.",
            "severity": "moderate",
            "mechanism": "Combined beta-blockade.",
            "recommendation": "Monitor heart rate; consult the doctor.",
        }
    ]
)


async def _visit_record(client, member_id: str) -> str:
    resp = await client.post(
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
    return resp.json()["id"]


# ── WS1: visit_summary ───────────────────────────────────────────────────────


async def test_visit_summary_requires_record_id(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    patch_plan([FakeProvider()])
    member_id = await _member(insight_client)
    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/reports/visit-summary/stream"
    )
    assert resp.status_code == 422
    assert "record_id" in resp.json()["detail"]


async def test_visit_summary_unknown_record_404(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    patch_plan([FakeProvider()])
    member_id = await _member(insight_client)
    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/reports/visit-summary/stream",
        params={"record_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


async def test_visit_summary_roundtrip(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)
    record_id = await _visit_record(insight_client, member_id)

    events = await _read_sse(
        insight_client,
        "POST",
        f"/api/v1/members/{member_id}/reports/visit-summary/stream",
        params={"record_id": record_id},
    )
    assert events[-1]["stage"] == "complete", events
    report = events[-1]["report"]
    assert report["kind"] == "visit_summary"

    # The prompt carries THIS visit's data plus the member snapshot.
    prompt = provider.calls[0]["prompt"]
    assert "Dr. Rao" in prompt
    assert "Poor glycemic control" in prompt
    assert "Discussed diet and adherence" in prompt
    assert "Metformin" in prompt  # member context still present

    latest = await insight_client.get(
        f"/api/v1/members/{member_id}/reports/latest", params={"kind": "visit_summary"}
    )
    assert latest.status_code == 200, latest.text
    assert latest.json()["id"] == report["id"]
    assert latest.json()["sources"]["visit"]["record_id"] == record_id


# ── WS5: pre_consultation structured A5 note ─────────────────────────────────


async def test_pre_consultation_a5_structured(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    provider = FakeProvider(reply=A5_REPLY)
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)

    events = await _read_sse(
        insight_client,
        "POST",
        f"/api/v1/members/{member_id}/reports/pre-consultation/stream",
    )
    assert events[-1]["stage"] == "complete", events
    report = events[-1]["report"]

    # content is the plain-text A5 rendering, built by code from the payload;
    # the sheet date is ALWAYS code-stamped (never the model's guess).
    assert report["content"].startswith(f"Date: {date.today().isoformat()}")
    assert "Member Name: Asha" in report["content"]
    assert "Chronic: Type 2 Diabetes Mellitus" in report["content"]
    assert "C/c: burning feet at night" in report["content"]
    assert "To discuss with doctor" in report["content"]
    assert "1. HbA1c 8.4% above target" in report["content"]

    sources = report["sources"]
    assert sources["structured_ok"] is True
    assert len(sources["a5_note"]["to_discuss"]) == 3
    assert sources["a5_note"]["current_medications"] == [
        "Metformin 500 mg",
        "Met XL 25 mg",
    ]
    # The schema block is in the prompt (rendered from the Pydantic model).
    assert "PRE-CONSULTATION A5 NOTE SCHEMA" in provider.calls[0]["prompt"]


async def test_pre_consultation_a5_fallback_on_bad_reply(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    provider = FakeProvider()  # narrative text — not valid JSON
    patch_plan([provider])
    member_id = await _member(insight_client)
    await _seed_meds_labs(insight_client, member_id)

    events = await _read_sse(
        insight_client,
        "POST",
        f"/api/v1/members/{member_id}/reports/pre-consultation/stream",
    )
    assert events[-1]["stage"] == "complete", events
    report = events[-1]["report"]
    # Unusable reply → deterministic code-built note, never a failure.
    assert report["sources"]["structured_ok"] is False
    assert report["content"].startswith("Date:")
    assert "Metformin 500 mg" in report["content"]


# ── WS2: pair drug interactions ──────────────────────────────────────────────


async def test_pair_interaction_roundtrip(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    provider = FakeProvider(reply=PAIR_REPLY)
    patch_plan([provider])
    member_id = await _member(insight_client)

    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/drug-interactions/pair",
        json={"medicine_a": "Met XL", "medicine_b": "CardiCare"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["medicines_checked"] == 2
    assert body["interactions"][0]["severity"] == "moderate"
    assert body["interactions"][0]["drugs"] == ["Met XL", "CardiCare"]

    # Both names reached the prompt; member context is attached.
    prompt = provider.calls[0]["prompt"]
    assert "DRUG A: Met XL" in prompt
    assert "DRUG B: CardiCare" in prompt
    assert "Patient: Asha." in prompt

    listing = await insight_client.get(
        "/api/v1/insights", params={"member_id": member_id, "kind": "drug_interactions_pair"}
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_pair_interaction_validation(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    patch_plan([FakeProvider()])
    member_id = await _member(insight_client)
    resp = await insight_client.post(
        f"/api/v1/members/{member_id}/drug-interactions/pair",
        json={"medicine_a": "  ", "medicine_b": "CardiCare"},
    )
    assert resp.status_code == 422


async def test_pair_interaction_respects_consent(insight_client, patch_plan):  # noqa: F811 — pytest fixture param
    provider = FakeProvider(name="local-ollama", reply=PAIR_REPLY)
    captured = patch_plan([provider])
    member_id = await _member(insight_client, consent=False)
    await insight_client.post(
        f"/api/v1/members/{member_id}/drug-interactions/pair",
        json={"medicine_a": "A", "medicine_b": "B"},
    )
    assert captured["local_only"] is True


# ── WS4: price comparison + catalog refresh ──────────────────────────────────


async def _seed_sample_catalog(session_factory, tmp_path):
    sample = tmp_path / "sample.csv"
    sample.write_text(
        "product_id,name,composition,price,package\n"
        "1,Metformin 500mg Tablet,Metformin (500mg),3.2,10's\n"
        "2,Metformin 500mg Tablet SR,Metformin (500mg),4.0,10's\n"
        "3,Glimepiride 1mg Tablet,Glimepiride (1mg),2.5,10's\n"
    )
    async with session_factory() as db:
        seeded = await local_drug_service.seed_local_drugs(db, sample)
        await db.commit()
    assert seeded == 3


async def test_price_compare_table(session_factory, tmp_path, auth_client):
    await _seed_sample_catalog(session_factory, tmp_path)
    resp = await auth_client.post(
        "/api/v1/drugs/price-compare",
        json={"medicines": ["Metformin 500mg Tablet", "Totally Unknown Drug"], "narrate": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["narrative"] is None
    exact = body["items"][0]
    assert exact["match"] == "exact"
    assert exact["price"] == 3.2  # cheapest exact match wins
    assert exact["ingredients"] == "Metformin"
    assert body["items"][1]["match"] is None
    assert body["items"][1]["price"] is None
    assert body["matched_count"] == 1
    assert body["total_price"] == 3.2


async def test_price_compare_ignores_dose_and_form_words(
    session_factory, tmp_path, auth_client
):
    """Normalization strips dose/form words, so '850 tablet' still matches."""
    await _seed_sample_catalog(session_factory, tmp_path)
    resp = await auth_client.post(
        "/api/v1/drugs/price-compare",
        json={"medicines": ["metformin 850 tablet"], "narrate": False},
    )
    items = resp.json()["items"]
    assert items[0]["match"] == "exact"
    assert "Metformin" in items[0]["catalog_name"]
    assert items[0]["price"] == 3.2  # cheapest of the exact matches


async def test_price_compare_grounds_narrative(
    session_factory, tmp_path, auth_client, patch_plan  # noqa: F811 — pytest fixture param
):
    await _seed_sample_catalog(session_factory, tmp_path)
    provider = FakeProvider(reply="Metformin is 3.2; the unknown drug is unmatched.")
    patch_plan([provider])
    member_id = await _member(auth_client)

    resp = await auth_client.post(
        "/api/v1/drugs/price-compare",
        json={
            "medicines": ["Metformin 500mg Tablet", "Totally Unknown Drug"],
            "member_id": member_id,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["narrative"] == "Metformin is 3.2; the unknown drug is unmatched."
    assert body["provider_used"] == "fake"

    # The narrative prompt carries ONLY the computed table (grounding).
    prompt = provider.calls[0]["prompt"]
    assert '"total_price": 3.2' in prompt
    assert '"match": null' in prompt

    listing = await auth_client.get(
        "/api/v1/insights", params={"member_id": member_id, "kind": "price_comparison"}
    )
    assert len(listing.json()) == 1


async def test_price_compare_rejects_over_limit(session_factory, tmp_path, auth_client):
    resp = await auth_client.post(
        "/api/v1/drugs/price-compare",
        json={"medicines": [f"Med{i}" for i in range(16)], "narrate": False},
    )
    assert resp.status_code == 422


async def test_refresh_catalog_disabled_without_url(monkeypatch):
    monkeypatch.setattr(
        local_drug_service,
        "get_settings",
        lambda: SimpleNamespace(JAN_AUSHADHI_DATASET_URL=""),
    )
    result = await local_drug_service.refresh_catalog()
    assert result["status"] == "disabled"


async def test_refresh_catalog_failure_keeps_rows(monkeypatch):
    monkeypatch.setattr(
        local_drug_service,
        "get_settings",
        lambda: SimpleNamespace(JAN_AUSHADHI_DATASET_URL="http://127.0.0.1:1/nope.csv"),
    )
    result = await local_drug_service.refresh_catalog()
    assert result["status"] == "error"
