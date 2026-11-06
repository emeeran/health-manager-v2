"""Smart search / smart entry with injected fake providers (no network).

AI callables are patched at module scope (`ai_router.build_plan`, the
upstream pattern from test_ai_extraction.py); conftest already points
Ollama at a closed port, so a missing patch can never reach a real
provider — those tests assert the 503/fallback path instead.
"""

import json

import pytest_asyncio

from app.services.ai import router as ai_router
from tests.test_search_dashboard import _create_member, _create_record, _ensure_router


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
        return self.reply or "{}"


@pytest_asyncio.fixture
def smart_client(auth_client):
    from app.main import app
    from app.routers import smart_entry, smart_search

    _ensure_router(app, smart_search.router)
    _ensure_router(app, smart_entry.router)
    return auth_client


# ── smart search ──────────────────────────────────────────────────────


async def test_smart_search_grounding_and_filters(smart_client):
    asha = await _create_member(smart_client, "Asha")
    rahul = await _create_member(smart_client, "Rahul")
    await _create_record(
        smart_client, asha["id"], diagnosis="Type 2 Diabetes review", summary="A1c 7.2"
    )
    await _create_record(
        smart_client, rahul["id"], diagnosis="Fracture follow-up", summary="cast removed"
    )

    provider = FakeProvider(
        reply=json.dumps(
            {
                "member_name": "Asha",
                "record_types": ["doctor_visit"],
                "date_from": None,
                "date_to": None,
                "keywords": ["diabetes"],
            }
        )
    )

    def fake_build(local_only: bool = False):
        return [provider]

    original = ai_router.build_plan
    ai_router.build_plan = fake_build
    try:
        resp = await smart_client.post(
            "/api/v1/smart-search", json={"question": "what did Asha's diabetes visit say?"}
        )
    finally:
        ai_router.build_plan = original
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai_powered"] is True

    # Grounding: the model only ever saw the deterministic member roster,
    # never raw records — and it can't inject facts into the results.
    assert provider.calls, "provider was never called"
    prompt = provider.calls[0]["prompt"]
    assert "Asha (self)" in prompt or "Asha (" in prompt
    assert "Return the JSON filters" in prompt

    results = body["results"]
    assert len(results) == 1
    hit = results[0]
    assert hit["member_name"] == "Asha"
    assert hit["diagnosis"] == "Type 2 Diabetes review"
    assert hit["record_type"] == "doctor_visit"
    assert hit["record_date"] == "2026-05-01"


async def test_smart_search_records_alias_matches_v1_shape(smart_client):
    asha = await _create_member(smart_client, "Asha")
    await _create_record(smart_client, asha["id"], diagnosis="Asthma plan")
    provider = FakeProvider(
        reply=json.dumps({"member_name": None, "record_types": [], "keywords": ["asthma"]})
    )
    original = ai_router.build_plan
    ai_router.build_plan = lambda local_only=False: [provider]
    try:
        resp = await smart_client.post("/api/v1/smart-search/records", json={"query": "asthma"})
    finally:
        ai_router.build_plan = original
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai_powered"] is True
    assert [r["diagnosis"] for r in body["results"]] == ["Asthma plan"]


async def test_smart_search_falls_back_to_keywords_without_ai(smart_client):
    """No provider reachable (Ollama on a closed port, no cloud keys):
    deterministic keyword search, ai_powered False — never a hang."""
    asha = await _create_member(smart_client, "Asha")
    await _create_record(smart_client, asha["id"], diagnosis="Asthma plan")
    resp = await smart_client.post("/api/v1/smart-search", json={"question": "asthma"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai_powered"] is False
    assert [r["diagnosis"] for r in body["results"]] == ["Asthma plan"]


async def test_smart_search_rejects_short_query(smart_client):
    resp = await smart_client.post("/api/v1/smart-search", json={"question": "a"})
    assert resp.status_code == 422


# ── smart entry ───────────────────────────────────────────────────────


DRAFT_REPLY = json.dumps(
    {
        "member_name": "Rahul",
        "record_type": "doctor_visit",
        "record_date": "2026-05-03",
        "diagnosis": "Acute pharyngitis",
        "summary": "Throat pain for 3 days",
        "provider_name": "Dr Rao",
        "medications": [{"medicine": "Amoxicillin", "dosage": "500 mg", "timing": "thrice daily"}],
        "labs": [
            {
                "test_name": "CRP",
                "result": "18",
                "units": "mg/L",
                "value_num": 18.0,
                "flag": "high",
            }
        ],
        "vitals": [
            {
                "vital_type": "temperature",
                "value_num": 101.2,
                "unit": "F",
            },
            {"vital_type": "not_a_vital", "value_num": 1},
        ],
        "confidence": "high",
    }
)


async def test_smart_entry_parse_draft_not_saved(smart_client):
    await _create_member(smart_client, "Asha")
    rahul = await _create_member(smart_client, "Rahul")
    provider = FakeProvider(reply=DRAFT_REPLY)
    original = ai_router.build_plan
    ai_router.build_plan = lambda local_only=False: [provider]
    try:
        resp = await smart_client.post(
            "/api/v1/smart-entry",
            json={"text": "Rahul saw Dr Rao yesterday, throat pain, fever 101.2"},
        )
    finally:
        ai_router.build_plan = original
    assert resp.status_code == 200, resp.text
    draft = resp.json()

    # Member resolution is deterministic code over the roster.
    assert draft["member"]["id"] == rahul["id"]
    assert draft["member"]["matched_by"] == "name"
    assert draft["record_type"] == "doctor_visit"
    assert draft["confidence"] == "high"
    assert draft["medications"][0]["medicine"] == "Amoxicillin"
    assert draft["labs"][0]["flag"] == "high"
    # Invalid vital types are dropped, not invented.
    assert [v["vital_type"] for v in draft["vitals"]] == ["temperature"]
    assert any(f["label"] == "Vitals" for f in draft["preview_fields"])

    # Draft must not persist anything.
    meds = (await smart_client.get(f"/api/v1/members/{rahul['id']}/medications")).json()
    labs = (await smart_client.get(f"/api/v1/members/{rahul['id']}/labs")).json()
    assert meds == [] and labs == []


async def test_smart_entry_relationship_match_and_low_confidence(smart_client):
    await _create_member(smart_client, "Asha")
    # Create Rahul as a child so the relationship path can match "son".
    resp = await smart_client.post(
        "/api/v1/members", json={"name": "Rahul", "relationship": "child"}
    )
    assert resp.status_code == 201, resp.text
    rahul = resp.json()

    provider = FakeProvider(reply=json.dumps({"member_name": "son", "confidence": "medium"}))
    original = ai_router.build_plan
    ai_router.build_plan = lambda local_only=False: [provider]
    try:
        resp = await smart_client.post("/api/v1/smart-entry", json={"text": "son had a fever"})
    finally:
        ai_router.build_plan = original
    assert resp.status_code == 200, resp.text
    draft = resp.json()
    assert draft["member"]["id"] == rahul["id"]
    assert draft["member"]["matched_by"] == "relationship"


async def test_smart_entry_default_member_is_low_confidence(smart_client):
    asha = await _create_member(smart_client, "Asha")
    provider = FakeProvider(reply=json.dumps({"member_name": None}))
    original = ai_router.build_plan
    ai_router.build_plan = lambda local_only=False: [provider]
    try:
        resp = await smart_client.post("/api/v1/smart-entry", json={"text": "fever since morning"})
    finally:
        ai_router.build_plan = original
    draft = resp.json()
    assert draft["member"]["id"] == asha["id"]
    assert draft["member"]["matched_by"] == "default"
    assert draft["confidence"] == "low"


async def test_smart_entry_confirm_persists_entities(smart_client):
    asha = await _create_member(smart_client, "Asha")
    provider = FakeProvider(reply=DRAFT_REPLY)
    original = ai_router.build_plan
    ai_router.build_plan = lambda local_only=False: [provider]
    try:
        draft = (
            await smart_client.post("/api/v1/smart-entry", json={"text": "Rahul saw Dr Rao"})
        ).json()
    finally:
        ai_router.build_plan = original

    confirm = {
        "member_id": asha["id"],
        "record_type": draft["record_type"],
        "record_date": draft["record_date"],
        "diagnosis": draft["diagnosis"],
        "summary": draft["summary"],
        "provider_name": draft["provider_name"],
        "medications": draft["medications"],
        "labs": draft["labs"],
        "vitals": [{**v, "vital_type": v["vital_type"]} for v in draft["vitals"]],
    }
    resp = await smart_client.post("/api/v1/smart-entry/confirm", json=confirm)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["medication_ids"]) == 1
    assert len(body["lab_ids"]) == 1
    assert len(body["vital_ids"]) == 1
    assert body["record_id"]

    meds = (await smart_client.get(f"/api/v1/members/{asha['id']}/medications")).json()
    assert meds[0]["medicine"] == "Amoxicillin"
    labs = (await smart_client.get(f"/api/v1/members/{asha['id']}/labs")).json()
    assert labs[0]["test_name"] == "CRP" and labs[0]["flag"] == "high"
    vitals = (await smart_client.get(f"/api/v1/members/{asha['id']}/vitals")).json()
    assert vitals[0]["vital_type"] == "temperature"
    records = (await smart_client.get(f"/api/v1/members/{asha['id']}/records")).json()
    assert records[0]["diagnosis"] == "Acute pharyngitis"


async def test_smart_entry_parse_requires_provider(smart_client):
    """No provider reachable: 503, never a hang on a real provider."""
    await _create_member(smart_client, "Asha")
    resp = await smart_client.post("/api/v1/smart-entry", json={"text": "fever today"})
    assert resp.status_code == 503


async def test_smart_entry_confirm_requires_member(smart_client):
    resp = await smart_client.post(
        "/api/v1/smart-entry/confirm",
        json={"member_id": str(__import__("uuid").uuid4()), "medications": []},
    )
    assert resp.status_code == 404
