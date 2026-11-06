"""Attachment upload/download flow against the encrypted store."""

import hashlib

from app.core import storage

PDF_BYTES = b"%PDF-1.4 consultation report test payload"


async def _setup_record(client) -> tuple[str, str]:
    member = (await client.post("/api/v1/members", json={"name": "Asha"})).json()
    record = (
        await client.post(
            f"/api/v1/members/{member['id']}/records",
            json={"record_type": "lab_report", "record_date": "2026-02-20"},
        )
    ).json()
    return member["id"], record["id"]


async def test_upload_download_roundtrip(auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    member_id, record_id = await _setup_record(auth_client)

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record_id}/attachments",
        files=[("files", ("report.pdf", PDF_BYTES, "application/pdf"))],
    )
    assert resp.status_code == 201, resp.text
    attachment = resp.json()[0]
    assert attachment["original_name"] == "report.pdf"
    assert attachment["content_hash"] == hashlib.sha256(PDF_BYTES).hexdigest()
    assert attachment["file_size"] == len(PDF_BYTES)

    downloaded = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == PDF_BYTES
    assert "attachment" in downloaded.headers["content-disposition"]

    preview = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/preview")
    assert preview.status_code == 200
    assert "inline" in preview.headers["content-disposition"]


async def test_upload_dedups_identical_file_per_record(auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    member_id, record_id = await _setup_record(auth_client)
    url = f"/api/v1/members/{member_id}/records/{record_id}/attachments"
    files = [("files", ("same.pdf", PDF_BYTES, "application/pdf"))]

    first = (await auth_client.post(url, files=files)).json()
    second = (await auth_client.post(url, files=files)).json()
    assert first[0]["id"] == second[0]["id"]  # deduped to the existing row


async def test_upload_rejects_bad_content(auth_client, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    member_id, record_id = await _setup_record(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/{record_id}/attachments",
        files=[("files", ("evil.pdf", b"definitely not a pdf", "application/pdf"))],
    )
    assert resp.status_code == 415


async def test_download_scoped_across_households(client, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    await client.post(
        "/api/v1/auth/register", json={"username": "dl_owner", "password": "Password1!"}
    )
    member_id, record_id = await _setup_record(client)
    attachment = (
        await client.post(
            f"/api/v1/members/{member_id}/records/{record_id}/attachments",
            files=[("files", ("r.pdf", PDF_BYTES, "application/pdf"))],
        )
    ).json()[0]

    await client.post(
        "/api/v1/auth/register", json={"username": "dl_other", "password": "Password1!"}
    )
    resp = await client.get(f"/api/v1/attachments/{attachment['id']}/download")
    assert resp.status_code == 404
