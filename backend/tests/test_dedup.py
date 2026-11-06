"""check-filenames: duplicate upload warning endpoint."""

from tests.test_thumbnails import make_png_bytes, make_pdf_bytes


async def _upload(client, record_date, filename, file_bytes, mime):
    existing = (await client.get("/api/v1/members")).json()
    member = (
        existing[0]
        if existing
        else (await client.post("/api/v1/members", json={"name": "Tester"})).json()
    )
    record = (
        await client.post(
            f"/api/v1/members/{member['id']}/records",
            json={"record_type": "lab_report", "record_date": record_date},
        )
    ).json()
    await client.post(
        f"/api/v1/members/{member['id']}/records/{record['id']}/attachments",
        files=[("files", (filename, file_bytes, mime))],
    )
    return member["id"]


async def test_check_filenames_matches_case_insensitive(auth_client, tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    member_id = await _upload(
        auth_client, "2026-05-01", "CBC-Report.pdf", make_pdf_bytes(), "application/pdf"
    )
    await _upload(auth_client, "2026-05-02", "xray.png", make_png_bytes(), "image/png")

    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records/check-filenames",
        json={"filenames": ["cbc-report.PDF", "unknown.pdf", "  XRAY.png "]},
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert {m["filename"] for m in matches} == {"CBC-Report.pdf", "xray.png"}
    dates = {m["record_date"] for m in matches}
    assert dates == {"2026-05-01", "2026-05-02"}


async def test_check_filenames_scoped_per_household(client, tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    await client.post("/api/v1/auth/register", json={"username": "fn_a", "password": "Password1!"})
    member_id = await _upload(
        client, "2026-05-01", "secret-scan.png", make_png_bytes(), "image/png"
    )
    # Second household's member must see no matches.
    await client.post("/api/v1/auth/register", json={"username": "fn_b", "password": "Password1!"})
    other_member = (await client.post("/api/v1/members", json={"name": "B"})).json()
    resp = await client.post(
        f"/api/v1/members/{other_member['id']}/records/check-filenames",
        json={"filenames": ["secret-scan.png"]},
    )
    assert resp.status_code == 200
    assert resp.json()["matches"] == []
    assert member_id  # silence unused-var linters


async def test_check_filenames_requires_body(auth_client):
    member = (await auth_client.post("/api/v1/members", json={"name": "V"})).json()
    resp = await auth_client.post(
        f"/api/v1/members/{member['id']}/records/check-filenames", json={}
    )
    assert resp.status_code == 422
