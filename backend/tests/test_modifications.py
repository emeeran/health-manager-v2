"""Modification-plan features: member current-medications (+ AI merge),
prescription ↔ doctor-visit linking, and batch-extraction classification.

AI callables are patched at module scope (same pattern as
test_smart_ai.py); conftest points Ollama at a closed port so an
unpatched call can never reach a real provider.
"""

import pytest_asyncio

from app.services.ai import router as ai_router
from tests.test_search_dashboard import _create_member


class FakeProvider:
    def __init__(self, name: str = "fake", reply: str = "") -> None:
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
        return self.reply


async def _patch_plan(provider):
    async def fake_plan(db, household_id, local_only: bool = True):
        return [provider] if provider else []

    original = ai_router.plan_for_household
    ai_router.plan_for_household = fake_plan
    return original


@pytest_asyncio.fixture
def api(auth_client):
    return auth_client


# ── member current_medications ────────────────────────────────────────


async def test_current_medications_roundtrip(api):
    member = await _create_member(api, "Asha")

    resp = await api.patch(
        f"/api/v1/members/{member['id']}",
        json={"current_medications": "Metformin — 500 mg, twice daily"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_medications"] == "Metformin — 500 mg, twice daily"

    # Nullable: clearing the field comes back as null, not an error.
    resp = await api.patch(f"/api/v1/members/{member['id']}", json={"current_medications": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_medications"] is None


async def test_merge_current_medications_suggestion(api):
    member = await _create_member(api, "Asha")
    await api.patch(
        f"/api/v1/members/{member['id']}",
        json={"current_medications": "Metformin — 500 mg"},
    )
    await api.post(
        f"/api/v1/members/{member['id']}/medications",
        json={"medicine": "Amlodipine", "dosage": "5 mg", "timing": "morning"},
    )

    provider = FakeProvider(reply="Metformin — 500 mg\nAmlodipine — 5 mg, morning")
    original = await _patch_plan(provider)
    try:
        resp = await api.post(f"/api/v1/members/{member['id']}/current-medications/merge")
    finally:
        ai_router.plan_for_household = original

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Metformin" in body["suggestion"]
    assert "Amlodipine" in body["suggestion"]
    # Nothing persisted — the member record is untouched until the client PATCHes.
    resp = await api.get(f"/api/v1/members/{member['id']}")
    assert resp.json()["current_medications"] == "Metformin — 500 mg"


async def test_merge_without_provider_is_503(api):
    member = await _create_member(api, "Asha")
    original = await _patch_plan(None)
    try:
        resp = await api.post(f"/api/v1/members/{member['id']}/current-medications/merge")
    finally:
        ai_router.plan_for_household = original
    assert resp.status_code == 503, resp.text


# ── prescription ↔ doctor-visit linking ───────────────────────────────


async def test_prescription_autofills_from_nearby_visit(api):
    member = await _create_member(api, "Asha")
    await _visit(api, member["id"], "2026-05-04", doctor_name="Dr Rao", diagnosis="Hypertension")

    resp = await api.post(
        f"/api/v1/members/{member['id']}/records",
        json={
            "record_type": "prescription",
            "record_date": "2026-05-06",
            "prescription_text": "Telmisartan 40 mg",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["doctor_name"] == "Dr Rao"
    assert body["diagnosis"] == "Hypertension"


async def test_prescription_standalone_without_nearby_visit(api):
    member = await _create_member(api, "Asha")
    await _visit(api, member["id"], "2026-01-10", doctor_name="Dr Rao", diagnosis="Old visit")

    resp = await api.post(
        f"/api/v1/members/{member['id']}/records",
        json={
            "record_type": "prescription",
            "record_date": "2026-05-06",
            "prescription_text": "Telmisartan 40 mg",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["doctor_name"] is None
    assert body["diagnosis"] is None


async def test_prescription_autofill_never_overwrites(api):
    member = await _create_member(api, "Asha")
    await _visit(api, member["id"], "2026-05-04", doctor_name="Dr Rao", diagnosis="Hypertension")

    resp = await api.post(
        f"/api/v1/members/{member['id']}/records",
        json={
            "record_type": "prescription",
            "record_date": "2026-05-05",
            "doctor_name": "Dr Meera",
            "prescription_text": "Telmisartan 40 mg",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["doctor_name"] == "Dr Meera"  # own value kept
    assert body["diagnosis"] == "Hypertension"  # empty field still filled


async def test_visit_autofill_scopes_to_member(api):
    asha = await _create_member(api, "Asha")
    rahul = await _create_member(api, "Rahul")
    await _visit(api, rahul["id"], "2026-05-04", doctor_name="Dr Rao", diagnosis="Flu")

    resp = await api.post(
        f"/api/v1/members/{asha['id']}/records",
        json={"record_type": "prescription", "record_date": "2026-05-05"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["doctor_name"] is None


async def _visit(api, member_id: str, date: str, **fields) -> dict:
    resp = await api.post(
        f"/api/v1/members/{member_id}/records",
        json={"record_type": "doctor_visit", "record_date": date, **fields},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── additional cloud providers + stored credentials ──────────────────


def _reset_settings_cache():
    from app.core.config import get_settings

    get_settings.cache_clear()


async def test_new_cloud_providers_join_the_plan(monkeypatch):
    """Gemini/Cohere/DeepSeek/Mistral/OpenRouter/HuggingFace activate from env keys."""
    from app.services.ai import router as ai_router

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    # The developer's backend/.env may hold real keys — pin the rest empty
    # so the absence assertion is deterministic.
    for name in ("COHERE", "MISTRAL", "OPENROUTER", "HUGGINGFACE"):
        monkeypatch.setenv(f"{name}_API_KEY", "")
    _reset_settings_cache()
    try:
        plan = ai_router.build_plan()
        by_name = {p.name: p for p in plan}
        assert "deepseek" in by_name and "gemini" in by_name
        assert by_name["deepseek"].base_url == "https://api.deepseek.com/v1"
        assert by_name["deepseek"].model == "deepseek-chat"
        # Providers without keys stay absent; no key → Ollama-only tail.
        assert "mistral" not in by_name
    finally:
        _reset_settings_cache()


async def test_stored_credentials_beat_env_in_household_plan(api, monkeypatch):
    """A key saved via Settings → AI providers overrides the env value."""
    from app.core.database import SessionLocal
    from app.services import provider_keys
    from app.services.ai import router as ai_router

    # Ensure deepseek is in the env-derived plan to begin with (conftest
    # blanks cloud keys; the developer's .env may or may not set this one).
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    _reset_settings_cache()
    try:
        async with SessionLocal() as db:
            await provider_keys.set_key(db, "DEEPSEEK_API_KEY", "sk-stored")
            await db.commit()

        plan = ai_router.build_plan()
        async with SessionLocal() as db:
            await provider_keys.apply_stored_credentials(db, plan)
        deepseek = next(p for p in plan if p.name == "deepseek")
        assert deepseek.api_key == "sk-stored"
    finally:
        _reset_settings_cache()


# ── primary provider + status/test endpoints ─────────────────────────


async def test_named_primary_provider_floats_to_front(monkeypatch):
    from app.services.ai import router as ai_router

    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    _reset_settings_cache()
    try:

        class _Empty:
            def all(self):
                return []  # no stored app_secrets

        class _DB:
            async def get(self, _model, _id):
                return None

            async def scalars(self, _query):
                return _Empty()

        resolved = await ai_router.plan_for_household(_DB(), "ignored")
        assert [p.name for p in resolved] != ["groq"]  # env order by default

        class _Cfg:
            settings_json = '{"primary_provider": "groq"}'

        class _DB2(_DB):
            async def get(self, model, _id):
                # Household lookup returns the config; AppSecret lookups (via
                # apply_stored_credentials) find nothing stored.
                return _Cfg() if getattr(model, "__name__", "") == "Household" else None

        resolved = await ai_router.plan_for_household(_DB2(), "ignored")
        assert [p.name for p in resolved][0] == "groq"
        assert {p.name for p in resolved} >= {"groq", "deepseek"}

        # Household "order" re-ranks the chain; unranked providers trail in
        # their env order.
        cfg = '{"order": ["deepseek", "groq"]}'

        class _Cfg2:
            settings_json = cfg

        class _DB3(_DB):
            async def get(self, model, _id):
                return _Cfg2() if getattr(model, "__name__", "") == "Household" else None

        resolved = await ai_router.plan_for_household(_DB3(), "ignored")
        names = [p.name for p in resolved]
        assert names[:2] == ["deepseek", "groq"]
        # Env-plan-only providers that aren't ranked still follow.
        assert set(names) >= {"deepseek", "groq"}
    finally:
        _reset_settings_cache()


async def test_ai_provider_status_and_test_endpoints(auth_client, session_factory):
    from app.services.ai import router as ai_router
    from tests.test_modifications import FakeProvider

    provider = FakeProvider(name="fake-status", reply="OK")

    def fake_build(local_only: bool = False):
        return [provider]

    original = ai_router.build_plan
    ai_router.build_plan = fake_build
    try:
        status = await auth_client.get("/api/v1/system/ai-providers")
        assert status.status_code == 200, status.text
        assert [p["name"] for p in status.json()["providers"]] == ["fake-status"]

        result = await auth_client.post("/api/v1/system/ai-providers/fake-status/test")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["ok"] is True
        assert body["model"] == "fake-model"
        assert isinstance(body["latency_ms"], int)

        missing = await auth_client.post("/api/v1/system/ai-providers/nope/test")
        assert missing.status_code == 404
    finally:
        ai_router.build_plan = original
        ai_router.health_cache._state.pop("fake-status", None)


async def test_ai_provider_models_endpoint(auth_client):
    """The settings board's Refresh fetches the live catalogue per provider."""
    from app.services.ai import router as ai_router
    from tests.test_modifications import FakeProvider

    class ListingProvider(FakeProvider):
        async def list_models(self):
            return ["m-b", "m-a"]

    class BrokenListProvider(FakeProvider):
        async def list_models(self):
            raise RuntimeError("catalogue unavailable")

    def fake_build(local_only: bool = False):
        return [
            ListingProvider(name="fake-list", reply="OK"),
            BrokenListProvider(name="fake-broken-list", reply=""),
        ]

    original = ai_router.build_plan
    ai_router.build_plan = fake_build
    try:
        listing = await auth_client.get("/api/v1/system/ai-providers/fake-list/models")
        assert listing.status_code == 200, listing.text
        assert listing.json()["models"] == ["m-a", "m-b"]  # sorted

        broken = await auth_client.get("/api/v1/system/ai-providers/fake-broken-list/models")
        assert broken.status_code == 502
        assert "catalogue unavailable" in broken.json()["detail"]

        missing = await auth_client.get("/api/v1/system/ai-providers/nope/models")
        assert missing.status_code == 404
    finally:
        ai_router.build_plan = original


async def test_ai_provider_test_reports_failure(auth_client):
    from app.services.ai import router as ai_router

    class BrokenProvider(FakeProvider):
        """Named fake-broken below."""

        async def complete(self, prompt: str, **kwargs) -> str:
            raise RuntimeError("connection refused")

    def fake_build(local_only: bool = False):
        return [BrokenProvider(name="fake-broken", reply="")]

    original = ai_router.build_plan
    ai_router.build_plan = fake_build
    try:
        result = await auth_client.post("/api/v1/system/ai-providers/fake-broken/test")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["ok"] is False
        assert "connection refused" in body["error"]
    finally:
        ai_router.build_plan = original
        ai_router.health_cache._state.pop("fake-broken", None)
