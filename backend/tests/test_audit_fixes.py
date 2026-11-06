"""Regression tests for the audit-fix batch (records, growth, extraction).

Each test pins one defect found in the pre-cleanup audit:
- investigations silently dropped on create / never returned on read
- apply-extraction duplicating lab/vital rows on retry
- growth report 500ing on non-positive measurements
- NaN/Infinity accepted by vital schemas
- mislabeled extraction uploads decoding to 500 instead of 415
- verification rows stranded PENDING when the verifier crashes
- unbounded attachment uploads
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Verification
from app.models.verification import VerificationStatus
from app.services.ai.verification import run_verification
from app.services.growth_service import LmsPoint, z_score
from tests.test_thumbnails import make_png_bytes


async def _member(client, name="Asha") -> str:
    return (await client.post("/api/v1/members", json={"name": name})).json()["id"]


# ── investigations round-trip ─────────────────────────────────────────


async def test_investigations_round_trip(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-11-01",
            "investigations": "CBC, HbA1c ordered",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["investigations"] == "CBC, HbA1c ordered"

    got = await auth_client.get(f"/api/v1/members/{member_id}/records/{resp.json()['id']}")
    assert got.status_code == 200
    assert got.json()["investigations"] == "CBC, HbA1c ordered"


# ── apply-extraction idempotency ──────────────────────────────────────


async def test_apply_extraction_reapply_does_not_duplicate(auth_client):
    member_id = await _member(auth_client)
    record = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/records",
            json={"record_type": "doctor_visit", "record_date": "2026-11-01"},
        )
    ).json()
    payload = {
        "clinical_data": {
            "labs": [{"name": "HbA1c", "result": "7.8", "units": "%", "reference": "4.0-6.0"}],
            "vitals": [{"type": "weight", "value": 82.5, "unit": "kg"}],
        },
    }
    url = f"/api/v1/members/{member_id}/records/{record['id']}/apply-extraction"
    first = await auth_client.post(url, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["labs_created"] == 1
    assert first.json()["vitals_created"] == 1

    # Retry (response lost after the server committed) must not duplicate.
    second = await auth_client.post(url, json=payload)
    assert second.status_code == 200
    assert second.json() == {"record_id": record["id"], "labs_created": 0, "vitals_created": 0}

    labs = (await auth_client.get(f"/api/v1/members/{member_id}/labs")).json()
    assert len(labs) == 1


# ── growth: non-positive measurements ─────────────────────────────────


def test_z_score_rejects_non_positive_value():
    point = LmsPoint(age_months=12.0, l=0.5, m=9.0, s=0.12)
    with pytest.raises(ValueError):
        z_score(0.0, point)
    with pytest.raises(ValueError):
        z_score(-4.0, point)


async def test_growth_report_negative_reading_not_500(auth_client):
    member_id = await _member(auth_client, "Baby")
    dob = (datetime.now(UTC) - timedelta(days=365)).date().isoformat()
    patched = await auth_client.patch(
        f"/api/v1/members/{member_id}", json={"birth_date": dob, "sex": "female"}
    )
    assert patched.status_code == 200, patched.text
    vital = await auth_client.post(
        f"/api/v1/members/{member_id}/vitals",
        json={
            "vital_type": "weight",
            "value_num": -3.0,
            "unit": "kg",
            "measured_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        },
    )
    assert vital.status_code == 201, vital.text
    resp = await auth_client.get(f"/api/v1/members/{member_id}/growth/report")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"] == []  # implausible reading skipped quietly


# ── NaN / Infinity rejection ──────────────────────────────────────────


async def test_vital_rejects_nan_and_inf(auth_client):
    member_id = await _member(auth_client)
    import json as _json

    for bad in ("NaN", "Infinity"):
        # Raw body: httpx's json= refuses non-compliant floats before send.
        resp = await auth_client.post(
            f"/api/v1/members/{member_id}/vitals",
            content=_json.dumps({"vital_type": "weight", "value_num": bad, "unit": "kg"}),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422, f"{bad}: {resp.text}"


# ── mislabeled extraction uploads ─────────────────────────────────────


async def test_extract_rejects_bytes_that_arent_the_claimed_type(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/extract",
        files=[("file", ("scan.pdf", b"not really a pdf", "application/pdf"))],
    )
    assert resp.status_code == 415, resp.text


# ── verification failure settles the row ──────────────────────────────


class ExplodingVerifier:
    name = "exploding"

    async def complete(self, prompt: str, **kwargs) -> str:
        raise RuntimeError("ollama is down")


async def test_run_verification_marks_failed_on_verifier_error(auth_client):
    from app.core.database import SessionLocal

    member_id = await _member(auth_client)
    async with SessionLocal() as db:
        row = Verification(
            member_id=uuid.UUID(member_id),
            subject_type="extraction",
            status=VerificationStatus.PENDING.value,
        )
        db.add(row)
        await db.commit()
        row_id = row.id

    await run_verification(row_id, "doc text", {"labs": []}, ExplodingVerifier())

    async with SessionLocal() as db:
        settled = await db.get(Verification, row_id)
        assert settled is not None
        assert settled.status == VerificationStatus.FAILED.value
        assert settled.completed_at is not None
        assert "ollama is down" in (settled.notes or "")


# ── attachment upload cap ─────────────────────────────────────────────


async def test_upload_attachments_caps_file_count(auth_client):
    member_id = await _member(auth_client)
    record = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/records",
            json={"record_type": "doctor_visit", "record_date": "2026-11-01"},
        )
    ).json()
    files = [("files", (f"f{i}.png", make_png_bytes(), "image/png")) for i in range(21)]
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/attachments", files=files
    )
    assert resp.status_code == 413, resp.text


# ── stored credentials materialize cloud providers (desktop fix) ──────


async def test_stored_keys_create_cloud_providers_without_env(auth_client, monkeypatch):
    """A desktop install has no shell env: a stored API key must create the
    provider, not just overlay attributes onto providers that don't exist."""
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Household
    from app.services.ai import router as ai_router
    from app.services.ai.ollama import OllamaProvider
    from app.services.provider_keys import set_key

    # Simulate the desktop env — no cloud key vars → build_plan (the
    # documented patch point) returns only the local tail.
    monkeypatch.setattr(
        ai_router,
        "build_plan",
        lambda local_only=False: [OllamaProvider()],
    )

    async with SessionLocal() as db:
        await set_key(db, "GROQ_API_KEY", "gsk-test-key")
        await db.commit()
        hid = (await db.scalars(select(Household))).first().id

        plan = await ai_router.plan_for_household(db, hid)
        names = [p.name for p in plan]
        assert "groq" in names, names
        groq = next(p for p in plan if p.name == "groq")
        assert groq.api_key == "gsk-test-key"
        # Cloud before the local tail; ollama always present.
        assert names.index("groq") < names.index("ollama")

        # Cloud consent off → local-only: stored keys must NOT leak cloud in.
        local_plan = await ai_router.plan_for_household(db, hid, local_only=True)
        assert [p.name for p in local_plan] == ["ollama"]


# ── verifier failover + tolerant verdict parsing ──────────────────────


class PassingVerifier:
    name = "passing"

    async def complete(self, prompt: str, **kwargs) -> str:
        return '{"verdict": "pass", "notes": ""}'


async def test_run_verification_fails_over_to_next_candidate(auth_client):
    """A dead verifier key must not sink verification — the next candidate
    in the list takes the audit and the row settles with its verdict."""
    from app.core.database import SessionLocal

    member_id = await _member(auth_client)
    async with SessionLocal() as db:
        row = Verification(
            member_id=uuid.UUID(member_id),
            subject_type="extraction",
            status=VerificationStatus.PENDING.value,
        )
        db.add(row)
        await db.commit()
        row_id = row.id

    await run_verification(
        row_id, "doc text", {"labs": []}, [ExplodingVerifier(), PassingVerifier()]
    )

    async with SessionLocal() as db:
        settled = await db.get(Verification, row_id)
        assert settled.status == VerificationStatus.PASSED.value
        assert settled.verifier_name == "passing"
        assert settled.completed_at is not None


def test_pick_verifiers_prefers_others_then_self():
    from app.services.ai.verification import pick_verifier, pick_verifiers

    class P:
        def __init__(self, name):
            self.name = name

    a, b, c = P("gemini"), P("groq"), P("ollama")
    plan = [a, b, c]
    # Others first, in plan order; the producer itself comes last.
    assert [p.name for p in pick_verifiers(plan, "groq")] == ["gemini", "ollama", "groq"]
    assert pick_verifier(plan, "groq").name == "gemini"
    # Self only when it's all there is.
    assert pick_verifier([a], "gemini").name == "gemini"
    assert pick_verifiers([], "gemini") == []


def test_parse_verdict_tolerates_fenced_and_chatty_output():
    from app.services.ai.verification import parse_verdict

    fenced = 'Sure! Here is my audit:\n```json\n{"verdict": "flag", "notes": "dose mismatch"}\n```'
    status, notes = parse_verdict(fenced)
    assert status == VerificationStatus.FLAGGED
    assert notes == "dose mismatch"

    status, _ = parse_verdict("total garbage")
    assert status == VerificationStatus.FAILED
