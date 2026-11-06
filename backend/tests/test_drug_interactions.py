"""Drug-interaction analysis endpoint (AI patched; deterministic snapshot)."""

import json
import uuid
from typing import Any

from sqlalchemy import select

from app.models import Insight
from app.models.medication import Medication, normalize_medicine_key
from app.services.ai import router as ai_router
from app.services.drug_interaction_service import parse_interactions


class FakeProvider:
    def __init__(self, reply: str | None = None, name: str = "fake") -> None:
        self.name = name
        self.model = "fake-model"
        self.local = name.startswith("local")
        self.timeout = 5
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.reply or ""


GOOD_REPLY = json.dumps(
    [
        {
            "drugs": ["Warfarin 5mg", "Aspirin 75mg"],
            "interaction": "Warfarin plus aspirin markedly increases bleeding risk.",
            "severity": "major",
            "mechanism": "Additive anticoagulant and antiplatelet effects.",
            "recommendation": "Ask the prescriber before combining.",
        }
    ]
)


async def _create_member(client, consent: bool = True) -> str:
    resp = await client.post("/api/v1/members", json={"name": "Asha", "cloud_ai_consent": consent})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_meds(session_factory, member_id: str, *names: str, status: str = "active") -> None:
    async with session_factory() as db:
        for name in names:
            db.add(
                Medication(
                    member_id=uuid.UUID(member_id),
                    medicine=name,
                    medicine_key=normalize_medicine_key(name),
                    dosage="once daily",
                    status=status,
                )
            )
        await db.commit()


async def test_interactions_analyzed_and_persisted(auth_client, session_factory, monkeypatch):
    member_id = await _create_member(auth_client)
    await _add_meds(session_factory, member_id, "Warfarin 5mg", "Aspirin 75mg")

    provider = FakeProvider(reply=GOOD_REPLY)

    def fake_build(local_only: bool = False):
        return [provider]

    monkeypatch.setattr(ai_router, "build_plan", fake_build)

    resp = await auth_client.post(f"/api/v1/members/{member_id}/drug-interactions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "fake"
    assert body["medications_checked"] == 2
    assert len(body["interactions"]) == 1
    interaction = body["interactions"][0]
    # Parser maps the clinical vocabulary onto the UI scale and shape.
    assert interaction["severity"] == "high"
    assert interaction["drugs"] == ["Warfarin 5mg", "Aspirin 75mg"]
    assert "bleeding" in interaction["description"]
    assert interaction["source"] == "ai"
    assert interaction["recommendation"]

    # The prompt carried the deterministic snapshot (names + dosages).
    prompt = provider.calls[0]["prompt"]
    assert "Warfarin 5mg" in prompt
    assert "Aspirin 75mg" in prompt

    # Persisted as an Insight (kind="drug_interactions").
    async with session_factory() as db:
        rows = (
            (await db.execute(select(Insight).where(Insight.kind == "drug_interactions")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].member_id == uuid.UUID(member_id)
    assert rows[0].provider_used == "fake"
    stored = json.loads(rows[0].content)
    assert stored[0]["severity"] == "high"
    snapshot = json.loads(rows[0].sources_json or "[]")
    assert [m["medicine"] for m in snapshot] == ["Warfarin 5mg", "Aspirin 75mg"]


async def test_interactions_fewer_than_two_meds_skips_ai(auth_client, session_factory, monkeypatch):
    member_id = await _create_member(auth_client)
    await _add_meds(session_factory, member_id, "Metformin 500mg")

    provider = FakeProvider(reply=GOOD_REPLY)

    def fake_build(local_only: bool = False):
        return [provider]

    monkeypatch.setattr(ai_router, "build_plan", fake_build)

    resp = await auth_client.post(f"/api/v1/members/{member_id}/drug-interactions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interactions"] == []
    assert body["provider_used"] is None
    assert not provider.calls, "AI must not be called for a single med"


async def test_interactions_inactive_meds_excluded(auth_client, session_factory, monkeypatch):
    member_id = await _create_member(auth_client)
    await _add_meds(
        session_factory,
        member_id,
        "Warfarin 5mg",
        "Aspirin 75mg",
        status="stopped",
    )
    provider = FakeProvider(reply=GOOD_REPLY)
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])

    resp = await auth_client.post(f"/api/v1/members/{member_id}/drug-interactions")
    assert resp.status_code == 200
    assert resp.json()["medications_checked"] == 0
    assert not provider.calls


async def test_interactions_unparseable_reply_degrades_to_empty(
    auth_client, session_factory, monkeypatch
):
    member_id = await _create_member(auth_client)
    await _add_meds(session_factory, member_id, "Warfarin 5mg", "Aspirin 75mg")

    provider = FakeProvider(reply="I'm sorry, I cannot analyze medications.")

    def fake_build(local_only: bool = False):
        return [provider]

    monkeypatch.setattr(ai_router, "build_plan", fake_build)

    resp = await auth_client.post(f"/api/v1/members/{member_id}/drug-interactions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interactions"] == []
    assert body["provider_used"] == "fake"


async def test_interactions_scoped_to_household(auth_client):
    resp = await auth_client.post(f"/api/v1/members/{uuid.uuid4()}/drug-interactions")
    assert resp.status_code == 404


async def test_cloud_consent_forces_local_plan(auth_client, session_factory, monkeypatch):
    member_id = await _create_member(auth_client, consent=False)
    await _add_meds(session_factory, member_id, "Warfarin 5mg", "Aspirin 75mg")

    captured: dict[str, bool] = {}
    provider = FakeProvider(reply=GOOD_REPLY, name="local-ollama")

    def fake_build(local_only: bool = False):
        captured["local_only"] = local_only
        return [provider]

    monkeypatch.setattr(ai_router, "build_plan", fake_build)

    resp = await auth_client.post(f"/api/v1/members/{member_id}/drug-interactions")
    assert resp.status_code == 200
    assert captured["local_only"] is True


# ── parser unit checks ───────────────────────────────────────────────


def test_parse_interactions_tolerates_fences_and_prose():
    reply = "Here is my analysis:\n```json\n" + GOOD_REPLY + "\n```\nDone."
    parsed = parse_interactions(reply)
    assert len(parsed) == 1
    assert parsed[0]["severity"] == "high"
    assert parsed[0]["drugs"] == ["Warfarin 5mg", "Aspirin 75mg"]


def test_parse_interactions_maps_severity_and_defaults_drugs():
    reply = json.dumps(
        [
            {"interaction": "minor upset", "severity": "minor"},
            {"interaction": "contraindicated combo", "severity": "contraindicated"},
            {"interaction": "no drugs listed", "severity": "moderate"},
        ]
    )
    parsed = parse_interactions(reply)
    assert [p["severity"] for p in parsed] == ["low", "high", "moderate"]
    assert parsed[2]["drugs"] == []
    assert parsed[2]["source"] == "ai"


def test_parse_interactions_drops_invalid_entries():
    reply = json.dumps(
        [
            {"interaction": "", "severity": "major"},
            "not a dict",
            {"interaction": "ok", "severity": "weird"},  # severity normalized
        ]
    )
    parsed = parse_interactions(reply)
    assert len(parsed) == 1
    assert parsed[0]["severity"] == "moderate"


def test_parse_interactions_empty_and_garbage():
    assert parse_interactions("") == []
    assert parse_interactions("garbage with no array") == []
