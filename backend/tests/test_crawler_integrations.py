"""Crawler-catalog integrations: chat grounding, interaction prompts,
drug-info catalog source, and allergy conflicts via catalog generics.

The crawled catalog is seeded through a small checkpoint SQLite (same rows
table shape as tools/crawl.py); AI providers are fakes that capture their
prompt so tests assert on the injected catalog context, never on model
output.
"""

import json
import sqlite3

import pytest


def _make_crawler_db(tmp_path, entries):
    path = tmp_path / "crawl.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE rows (url TEXT PRIMARY KEY, data TEXT)")
    conn.executemany(
        "INSERT INTO rows (url, data) VALUES (?, ?)",
        [(url, json.dumps(data)) for url, data in entries],
    )
    conn.commit()
    conn.close()
    return path


DUZELA = {
    "source": "1mg",
    "brand_name": "Zoltab Duzela 30 Capsule",
    "generic_name": "Duloxetine (30mg) + Methylcobalamin (1500mcg)",
    "manufacturer": "Sun Pharmaceutical Industries Ltd",
    "pack_size": "10 Capsule DR",
    "price_mrp": "231",
    "price_selling": "212",
    "uses": "Neuropathic pain; Fibromyalgia",
    "side_effects": "Nausea; Headache",
    "therapeutic_class": "NEURO CNS",
}


@pytest.fixture()
def catalog_db(tmp_path):
    return _make_crawler_db(
        tmp_path,
        [("https://www.1mg.com/drugs/zoltab-duzela-30-1", DUZELA)],
    )


async def _sync(session_factory, path):
    from app.services import crawler_drug_service

    async with session_factory() as db:
        outcome = await crawler_drug_service.sync_from_crawler_db(db, path)
    assert outcome["status"] == "ok"
    return outcome


async def test_drug_context_block_contains_generic_and_disclaimer(
    session_factory, catalog_db
):
    await _sync(session_factory, catalog_db)
    from app.services import crawler_drug_service

    async with session_factory() as db:
        block = await crawler_drug_service.drug_context_block(
            db, ["Zoltab Duzela 30 Capsule"]
        )
    assert "Duloxetine (30mg) + Methylcobalamin (1500mcg)" in block
    assert "Rs212" in block
    assert "untrusted" in block  # third-party text is flagged for the model

    async with session_factory() as db:
        empty = await crawler_drug_service.drug_context_block(
            db, ["Totally Unknown Drug"]
        )
    assert empty == ""


class CapturingStreamProvider:
    name = "fake"
    model = "fake"
    local = True
    timeout = 1

    def __init__(self):
        self.prompts = []

    async def available(self):
        return True

    async def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        return "ok"

    async def stream(self, prompt, system=None):
        self.prompts.append(prompt)

        async def gen():
            yield "ok"

        return gen()


async def test_chat_prompt_grounds_catalog_for_active_meds(
    session_factory, catalog_db, auth_client, monkeypatch
):
    await _sync(session_factory, catalog_db)
    from app.services.ai import router as ai_router
    import app.routers.conversations as conv_router

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    await auth_client.post(
        f"/api/v1/members/{member['id']}/medications",
        json={"medicine": "Zoltab Duzela 30 Capsule", "dosage": "30 mg"},
    )
    conversation = (
        await auth_client.post(
            "/api/v1/conversations",
            json={"member_id": member["id"], "title": "Consultation"},
        )
    ).json()

    provider = CapturingStreamProvider()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "Can I take it with food?"},
    ) as resp:
        assert resp.status_code == 200

    assert provider.prompts, "provider never received a prompt"
    prompt = provider.prompts[0]
    assert "Duloxetine (30mg) + Methylcobalamin (1500mcg)" in prompt
    assert "untrusted" in prompt


class CapturingCompleteProvider:
    name = "fake"

    def __init__(self):
        self.prompts = []

    async def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        return "[]"


async def test_pair_interaction_prompt_includes_catalog_context(
    session_factory, catalog_db, auth_client, monkeypatch
):
    await _sync(session_factory, catalog_db)
    from app.services.ai import router as ai_router

    member = (await auth_client.post("/api/v1/members", json={"name": "Vikram"})).json()
    provider = CapturingCompleteProvider()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])

    async def fake_first_available(plan):
        return provider

    monkeypatch.setattr(ai_router, "first_available", fake_first_available)

    resp = await auth_client.post(
        f"/api/v1/members/{member['id']}/drug-interactions/pair",
        json={"medicine_a": "Zoltab Duzela 30 Capsule", "medicine_b": "Paracetamol"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["interactions"] == []
    prompt = provider.prompts[0]
    assert "Duloxetine (30mg) + Methylcobalamin (1500mcg)" in prompt
    # matched drug → catalog block present; no "(no catalog data" fallback
    assert "(no catalog data" not in prompt


async def test_drug_info_resolves_catalog_first(session_factory, catalog_db, auth_client):
    await _sync(session_factory, catalog_db)
    member = (await auth_client.post("/api/v1/members", json={"name": "Meera"})).json()
    resp = await auth_client.get(
        f"/api/v1/members/{member['id']}/drug-info",
        params={"medicine": "Zoltab Duzela 30 Capsule"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "catalog"
    assert body["brand"] == "Zoltab Duzela 30 Capsule"
    assert body["generic"] == "Duloxetine (30mg) + Methylcobalamin (1500mcg)"
    assert body["price"] == 212
    assert body["url"].startswith("https://www.1mg.com/")


async def test_allergy_conflict_matches_catalog_generic(
    session_factory, catalog_db, auth_client
):
    await _sync(session_factory, catalog_db)
    member = (await auth_client.post("/api/v1/members", json={"name": "Rao"})).json()
    await auth_client.post(
        f"/api/v1/members/{member['id']}/allergies",
        json={"substance": "Duloxetine", "severity": "moderate"},
    )
    await auth_client.post(
        f"/api/v1/members/{member['id']}/medications",
        json={"medicine": "Zoltab Duzela 30 Capsule", "dosage": "30 mg"},
    )
    resp = await auth_client.get(f"/api/v1/members/{member['id']}/allergy-conflicts")
    assert resp.status_code == 200, resp.text
    conflicts = resp.json()
    assert len(conflicts) == 1
    assert conflicts[0]["matched_on"] == "catalog_generic"
    assert conflicts[0]["medication"] == "Zoltab Duzela 30 Capsule"
