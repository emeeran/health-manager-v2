"""Phase 10: record dedup/merge + confidentiality ceilings.

Merge invariant: idempotent — re-merging an already-merged duplicate into
the same primary is a 200 no-op; merging into a different primary is 409.
Confidentiality: private → admin only, caregiver → admin+member,
household → everyone; hidden records 404 (existence is information).
"""

import uuid
from datetime import date

import pytest


async def _create_member(client, name: str = "Dedup") -> str:
    resp = await client.post("/api/v1/members", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_record(
    client,
    member_id: str,
    clinical: dict | None = None,
    summary: str = "Note",
    record_type: str = "doctor_visit",
    confidentiality: str | None = None,
) -> dict:
    payload: dict = {
        "record_type": record_type,
        "record_date": "2026-05-01",
        "summary": summary,
    }
    if clinical is not None:
        payload["clinical_data"] = clinical
    if confidentiality:
        payload["confidentiality_level"] = confidentiality
    resp = await client.post(f"/api/v1/members/{member_id}/records", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _extra_client() -> object:
    from tests.test_household_admin import _extra_client as _f

    return _f()


async def _invite_and_accept(client, role: str, username: str):
    created = await client.post("/api/v1/household/users/invitations", json={"role": role})
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    new_client = _extra_client()
    accepted = await new_client.post(
        "/api/v1/household/users/invitations/accept",
        json={"token": token, "username": username, "password": "TestPass1!"},
    )
    assert accepted.status_code == 200, accepted.text
    return new_client


# ── dedup detection + merge ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_content_hash_duplicate_detection_and_merge(auth_client):
    member_id = await _create_member(auth_client)
    clinical = {
        "_type": "structured",
        "prescriptions": [
            {"medicine": "Metformin", "dosage": "500 mg", "timing": "bid", "duration": "30d"}
        ],
    }
    first = await _create_record(auth_client, member_id, clinical, summary="Original")
    twin = await _create_record(auth_client, member_id, clinical, summary="Copy")
    other = await _create_record(
        auth_client, member_id, {"diagnosis": "unrelated"}, summary="Other"
    )

    # Content hashes match for the identical payloads.
    assert first["content_hash"]
    assert first["content_hash"] == twin["content_hash"]
    assert other["content_hash"] != first["content_hash"]

    dup = await auth_client.get(f"/api/v1/members/{member_id}/records/duplicates")
    assert dup.status_code == 200, dup.text
    pairs = dup.json()["pairs"]
    match = next(
        p for p in pairs if {p["primary_id"], p["duplicate_id"]} == {first["id"], twin["id"]}
    )
    assert "identical_content" in match["reason"]
    assert match["score"] >= 3

    # Merge duplicate → primary. Primary keeps more content? The API picks
    # its own keeper for the pair, so merge whatever it flagged as duplicate.
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{match['duplicate_id']}/merge",
        json={"duplicate_of_id": match["primary_id"]},
    )
    assert resp.status_code == 200, resp.text
    primary = resp.json()
    assert primary["id"] == match["primary_id"]

    # The duplicate is gone from listings and marked merged.
    listed = (await auth_client.get(f"/api/v1/members/{member_id}/records")).json()
    ids = {r["id"] for r in listed}
    assert match["duplicate_id"] not in ids
    assert match["primary_id"] in ids

    fetched = await auth_client.get(f"/api/v1/members/{member_id}/records/{match['duplicate_id']}")
    assert fetched.status_code == 404


@pytest.mark.asyncio
async def test_merge_is_idempotent_and_consolidates_attachments(auth_client, session_factory):
    from sqlalchemy import select

    from app.models import Attachment, LabResult

    member_id = await _create_member(auth_client, "Mergey")
    clinical = {
        "_type": "structured",
        "prescriptions": [
            {"medicine": "Amlodipine", "dosage": "5 mg", "timing": "od", "duration": ""}
        ],
    }
    primary = await _create_record(auth_client, member_id, clinical, summary="Keep")
    duplicate = await _create_record(auth_client, member_id, clinical, summary="Dupe")

    # Hand-insert attachments + a lab referencing the duplicate.
    async with session_factory() as session:
        session.add_all(
            [
                Attachment(
                    record_id=uuid.UUID(duplicate["id"]),
                    file_path=f"files/aa/dup-{n}.bin",
                    content_hash=f"{'a' * 64}",
                    file_size=10,
                    mime="application/octet-stream",
                    original_name=f"scan-{n}.pdf",
                )
                for n in range(2)
            ]
        )
        session.add(
            LabResult(
                member_id=uuid.UUID(member_id),
                record_id=uuid.UUID(duplicate["id"]),
                test_name="HbA1c",
                result="6.2",
                record_date=date(2026, 5, 1),
            )
        )
        await session.commit()

    merge_url = f"/api/v1/members/{member_id}/records/{duplicate['id']}/merge"
    first_merge = await auth_client.post(merge_url, json={"duplicate_of_id": primary["id"]})
    assert first_merge.status_code == 200, first_merge.text

    async with session_factory() as session:
        from app.models import HealthRecord

        dup_row = await session.get(HealthRecord, uuid.UUID(duplicate["id"]))
        assert dup_row.is_deleted is True
        assert str(dup_row.merged_into_id) == primary["id"]
        atts = (
            await session.scalars(
                select(Attachment).where(Attachment.record_id == uuid.UUID(primary["id"]))
            )
        ).all()
        assert len(atts) == 2  # attachments consolidated onto the primary
        labs = (
            await session.scalars(
                select(LabResult).where(LabResult.record_id == uuid.UUID(primary["id"]))
            )
        ).all()
        assert len(labs) == 1  # lab re-pointed to the primary

    # Re-merge: idempotent no-op, still 200.
    re_merge = await auth_client.post(merge_url, json={"duplicate_of_id": primary["id"]})
    assert re_merge.status_code == 200, re_merge.text

    # Merging into a DIFFERENT primary now → 409.
    third = await _create_record(auth_client, member_id, None, summary="Third")
    conflict = await auth_client.post(merge_url, json={"duplicate_of_id": third["id"]})
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_merge_rejects_self_and_missing(auth_client):
    member_id = await _create_member(auth_client, "Edge")
    record = await _create_record(auth_client, member_id, None, summary="Solo")

    self_merge = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/merge",
        json={"duplicate_of_id": record["id"]},
    )
    assert self_merge.status_code == 400

    missing = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record['id']}/merge",
        json={"duplicate_of_id": str(uuid.uuid4())},
    )
    assert missing.status_code == 404


# ── confidentiality ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confidentiality_private_admin_only(auth_client):
    member_id = await _create_member(auth_client, "Private")
    private = await _create_record(
        auth_client, member_id, None, summary="Secret", confidentiality="private"
    )
    caregiver = await _create_record(
        auth_client, member_id, None, summary="Care", confidentiality="caregiver"
    )
    household = await _create_record(auth_client, member_id, None, summary="Open")

    # Admin sees everything, including the private record.
    admin_list = (await auth_client.get(f"/api/v1/members/{member_id}/records")).json()
    assert {r["id"] for r in admin_list} == {
        private["id"],
        caregiver["id"],
        household["id"],
    }
    got = await auth_client.get(f"/api/v1/members/{member_id}/records/{private['id']}")
    assert got.status_code == 200
    assert got.json()["confidentiality_level"] == "private"

    member_client = await _invite_and_accept(auth_client, "member", "membry")
    # Member sees caregiver + household but NOT private (404, not 403).
    member_list = (await member_client.get(f"/api/v1/members/{member_id}/records")).json()
    assert {r["id"] for r in member_list} == {caregiver["id"], household["id"]}
    hidden = await member_client.get(f"/api/v1/members/{member_id}/records/{private['id']}")
    assert hidden.status_code == 404

    viewer_client = await _invite_and_accept(auth_client, "viewer", "viewy")
    # Viewer sees household-level only.
    viewer_list = (await viewer_client.get(f"/api/v1/members/{member_id}/records")).json()
    assert {r["id"] for r in viewer_list} == {household["id"]}
    # ...and is blocked from writes by the middleware.
    blocked = await viewer_client.post(
        f"/api/v1/members/{member_id}/records",
        json={"record_type": "other", "record_date": "2026-05-02"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Viewer role is read-only"

    # Confidentiality is settable/updateable through the API.
    patched = await auth_client.patch(
        f"/api/v1/members/{member_id}/records/{household['id']}",
        json={"confidentiality_level": "private"},
    )
    assert patched.status_code == 200
    assert patched.json()["confidentiality_level"] == "private"
    now_hidden = await auth_client.get(f"/api/v1/members/{member_id}/records/{household['id']}")
    assert now_hidden.status_code == 200  # admin still sees it
    member_after = await member_client.get(f"/api/v1/members/{member_id}/records/{household['id']}")
    assert member_after.status_code == 404  # member lost access
