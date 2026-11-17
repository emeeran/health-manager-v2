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


def test_merge_chunk_results_template_sections():
    """Consolidated-report sections merge like the classic ones: lists
    concatenate, scalars first-wins."""
    from app.services.ai.extraction import merge_chunk_results

    merged = merge_chunk_results(
        [
            {
                "record_date": "2025-11-17",
                "patient": {"name": "J", "age": "48", "sex": "Female"},
                "clinical_history": "HMB x3 days",
                "exam_findings": "cervical ectopy",
                "imaging": [{"modality": "ultrasound", "region": "pelvis"}],
                "screenings": [{"type": "mammography", "grade": "BI-RADS 1"}],
                "labs": [{"name": "Hb", "result": "7.8"}],
            },
            {
                "record_date": "2025-11-15",  # earlier chunk date loses
                "patient": {"name": "OTHER"},
                "imaging": [{"modality": "x-ray", "region": "chest"}],
                "screenings": [{"type": "pap_smear", "grade": "NILM"}],
                "labs": [{"name": "Hb", "result": "9.2"}],
            },
        ]
    )
    assert merged["record_date"] == "2025-11-17"
    assert merged["patient"] == {"name": "J", "age": "48", "sex": "Female"}
    assert merged["clinical_history"] == "HMB x3 days"
    assert merged["exam_findings"] == "cervical ectopy"
    assert [i["modality"] for i in merged["imaging"]] == ["ultrasound", "x-ray"]
    assert [s["type"] for s in merged["screenings"]] == ["mammography", "pap_smear"]
    assert [row["result"] for row in merged["labs"]] == ["7.8", "9.2"]


def test_merge_chunk_results_optional_scalars():
    """A model reply carrying the optional scalar fields (encounter_no,
    ward, …) must merge, not KeyError — those keys were missing from the
    seed dict and every extraction that mentioned them crashed."""
    from app.services.ai.extraction import merge_chunk_results

    merged = merge_chunk_results(
        [{"encounter_no": "IP-2026-0042", "ward": "General", "phone": "555-0100"}]
    )
    assert merged["encounter_no"] == "IP-2026-0042"
    assert merged["ward"] == "General"
    assert merged["phone"] == "555-0100"
    assert merged["insurance"] is None


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


class ExplodingProvider(FakeProvider):
    """Provider whose complete() always raises (dead key, 400, 429, ...)."""

    def __init__(self, name: str = "exploding", error: Exception | None = None) -> None:
        super().__init__(name=name)
        self.error = error or RuntimeError("provider down")

    async def complete(self, prompt: str, **kwargs) -> str:
        raise self.error


async def test_failover_to_next_provider(auth_client, patch_plan):
    """A raising provider is skipped and the next in the plan serves the file."""
    dead = ExplodingProvider(name="boom-cloud")
    good = FakeProvider(name="backup")
    patch_plan([dead, good])
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_used"] == "backup"
    assert good.calls, "failover provider was never called"
    assert not dead.calls


async def test_failover_marks_provider_unhealthy(auth_client, patch_plan):
    """The failed provider is negative-cached so the next request skips it."""
    import time

    from app.services.ai import router as ai_router

    dead = ExplodingProvider(name="boom-cache")
    patch_plan([dead])
    member_id = await _create_member(auth_client)
    # Single dead provider: failover exhausts and the last error re-raises —
    # TestClient surfaces server exceptions instead of returning a 500.
    with pytest.raises(RuntimeError, match="provider down"):
        await auth_client.post(
            f"/api/v1/members/{member_id}/records/extract",
            files=[("file", ("note.png", make_png_bytes(), "image/png"))],
        )
    now = time.monotonic()
    assert ai_router.health_cache.get("boom-cache", now) is False


async def test_all_providers_failing_streams_error(auth_client, patch_plan):
    """Every provider down → SSE error event carries the last failure."""
    first = ExplodingProvider(name="boom-first", error=RuntimeError("first down"))
    second = ExplodingProvider(name="boom-second", error=RuntimeError("second down"))
    patch_plan([first, second])
    member_id = await _create_member(auth_client)
    events: list[dict] = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract/stream",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    stages = [e["stage"] for e in events]
    assert "failover" in stages
    assert stages[-1] == "error"
    assert "second down" in events[-1]["message"]


async def test_failover_progress_events(auth_client, patch_plan):
    """Each provider hop emits a failover progress event naming the loser."""
    dead = ExplodingProvider(name="boom-progress")
    good = FakeProvider(name="backup-progress")
    patch_plan([dead, good])
    member_id = await _create_member(auth_client)
    events: list[dict] = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract/stream",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    ) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    failovers = [e for e in events if e["stage"] == "failover"]
    assert len(failovers) == 1
    assert "boom-progress" in failovers[0]["message"]
    assert events[-1]["result"]["provider_used"] == "backup-progress"


def test_strip_report_markdown():
    from app.services.ai.extraction import strip_report_markdown

    assert strip_report_markdown("<think>hm</think>\n```markdown\n# Report\n```\n") == "# Report"
    assert strip_report_markdown("# Plain document\n") == "# Plain document"


async def test_extraction_includes_consolidated_report(auth_client, patch_plan):
    """The second pass fires with the report prompt and its output lands in
    clinical_data.consolidated_report."""
    provider = FakeProvider()
    patch_plan([provider])
    member_id = await _create_member(auth_client)
    body = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/records/extract",
            files=[("file", ("note.png", make_png_bytes(), "image/png"))],
        )
    ).json()
    report = body["clinical_data"]["consolidated_report"]
    assert isinstance(report, str) and report.strip()
    report_prompts = [c["prompt"] for c in provider.calls if "CONSOLIDATED CLINICAL & SURGICAL MEDICAL REPORT" in c["prompt"]]
    assert report_prompts, "report pass never called the provider"
    assert "Metformin" in report_prompts[0], "report prompt should carry the clinical data"


class ReportExplodingProvider(FakeProvider):
    """Healthy for extraction, dead for the report pass."""

    async def complete(self, prompt: str, **kwargs) -> str:
        if "CONSOLIDATED CLINICAL & SURGICAL MEDICAL REPORT" in prompt:
            raise RuntimeError("report pass down")
        return await super().complete(prompt, **kwargs)


async def test_report_failure_keeps_extraction(auth_client, patch_plan):
    """A failed report pass must not fail the extraction or add the key."""
    provider = ReportExplodingProvider(name="half-alive")
    patch_plan([provider])
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("note.png", make_png_bytes(), "image/png"))],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["clinical_data"]["diagnosis"] == "Type 2 Diabetes Mellitus"
    assert "consolidated_report" not in body["clinical_data"]
