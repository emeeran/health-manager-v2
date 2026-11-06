"""Extraction endpoints with injected fake providers (no network)."""

import json
from typing import Any

import pytest

from app.services.ai import router as ai_router
from tests.test_thumbnails import make_png_bytes


class FakeProvider:
    def __init__(self, name: str = "fake", reply: str | None = None) -> None:
        self.name = name
        self.model = "fake-model"
        self.local = name.startswith("local")
        self.timeout = 5
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.reply or json.dumps(
            {
                "record_date": "2026-04-02",
                "doctor_name": "Dr. Fake",
                "diagnosis": "Type 2 Diabetes Mellitus",
                "summary": "Started on metformin.",
                "medications": [{"name": "Metformin", "dosage": "500 mg", "duration_days": 30}],
                "labs": [],
                "vitals": [],
            }
        )


GOOD_REPLY = FakeProvider().reply
PASS_VERDICT = '{"verdict": "pass", "notes": ""}'


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


async def _create_member(client, consent: bool = True) -> str:
    resp = await client.post("/api/v1/members", json={"name": "Asha", "cloud_ai_consent": consent})
    return resp.json()["id"]


async def test_extract_blocking(auth_client, patch_plan):
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("note.pdf", make_png_bytes(), "image/png"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "fake"
    assert body["clinical_data"]["diagnosis"] == "Type 2 Diabetes Mellitus"
    assert body["clinical_data"]["medications"][0]["name"] == "Metformin"
    assert body["verification_id"]


async def test_extract_sse_stream_stages(auth_client, patch_plan):
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _create_member(auth_client)
    events: list[dict] = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract/stream",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    stages = [e["stage"] for e in events]
    assert stages[0] == "reading"
    assert "extracting" in stages
    assert stages[-1] == "complete"
    complete = events[-1]
    assert complete["result"]["provider_used"] == "fake"
    assert complete["result"]["verification_id"]


async def test_vision_path_passes_images(auth_client, patch_plan):
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _create_member(auth_client)
    await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("photo.png", make_png_bytes(), "image/png"))],
    )
    assert provider.calls, "provider was never called"
    assert provider.calls[0].get("images"), "vision path should attach images"


async def test_cloud_consent_forces_local_only(auth_client, patch_plan):
    provider = FakeProvider(name="local-ollama")
    captured = patch_plan([provider])
    member_id = await _create_member(auth_client, consent=False)
    await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    )
    assert captured["local_only"] is True

    member_id = await _create_member(auth_client, consent=True)
    await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    )
    assert captured["local_only"] is False


async def test_no_provider_available_returns_503(auth_client, monkeypatch):
    # Default env: Ollama at 127.0.0.1:1 (dead), no cloud keys.
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    )
    assert resp.status_code == 503


async def test_verification_completes_with_verdict(auth_client, patch_plan):
    extractor = FakeProvider(name="extractor")
    verifier = FakeProvider(name="verifier", reply=PASS_VERDICT)
    patch_plan([extractor, verifier])
    member_id = await _create_member(auth_client)
    body = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/records/extract",
            files=[("file", ("note.png", make_png_bytes(), "image/png"))],
        )
    ).json()

    # pick_verifier must choose the OTHER provider.
    from app.services.ai.verification import pick_verifier

    assert pick_verifier([extractor, verifier], "extractor").name == "verifier"

    vid = body["verification_id"]
    import asyncio

    for _ in range(30):
        poll = await auth_client.get(f"/api/v1/verifications/{vid}")
        if poll.json()["status"] != "pending":
            break
        await asyncio.sleep(0.1)
    final = poll.json()
    assert final["status"] == "passed"
    assert final["verifier_name"] == "verifier"


async def test_verification_flagged_notes(auth_client, patch_plan):
    from app.services.ai.verification import parse_verdict
    from app.models.verification import VerificationStatus

    status, notes = parse_verdict('{"verdict": "flag", "notes": "dose mismatch"}')
    assert status == VerificationStatus.FLAGGED
    assert notes == "dose mismatch"

    status, notes = parse_verdict("total garbage")
    assert status == VerificationStatus.FAILED


async def test_ai_status_offline(auth_client):
    resp = await auth_client.get("/api/v1/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_provider"] is None
    assert all(not p["available"] for p in body["providers"])


async def test_extract_rejects_bad_type(auth_client, patch_plan):
    patch_plan([FakeProvider()])
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("x.txt", b"plain text", "text/plain"))],
    )
    assert resp.status_code == 415
