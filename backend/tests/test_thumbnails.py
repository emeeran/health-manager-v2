"""Thumbnail + PDF page rendering endpoints."""

import struct
import zlib

import fitz


def make_png_bytes(color=(200, 30, 30), size=64) -> bytes:
    """Minimal valid PNG (solid color) built by hand — no Pillow needed."""
    width = height = size
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        data = tag + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def make_pdf_bytes(page_texts=("page one", "page two")) -> bytes:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


async def _upload(
    client, member_name="Asha", file_bytes=None, mime="image/png", filename="scan.png"
) -> tuple[str, str, dict]:
    member = (await client.post("/api/v1/members", json={"name": member_name})).json()
    record = (
        await client.post(
            f"/api/v1/members/{member['id']}/records",
            json={"record_type": "lab_report", "record_date": "2026-04-01"},
        )
    ).json()
    attachment = (
        await client.post(
            f"/api/v1/members/{member['id']}/records/{record['id']}/attachments",
            files=[("files", (filename, file_bytes or make_png_bytes(), mime))],
        )
    ).json()[0]
    return member["id"], record["id"], attachment


async def test_image_thumbnail(auth_client, tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    _, _, attachment = await _upload(auth_client)

    resp = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/thumbnail")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert resp.headers["cache-control"].startswith("public")

    # Content-addressed and cached on disk.
    cached = tmp_path / "thumbnails" / f"{attachment['content_hash']}.webp"
    assert cached.is_file()
    assert cached.read_bytes() == resp.content

    # Second request serves from cache (identical bytes).
    again = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/thumbnail")
    assert again.content == resp.content


async def test_pdf_thumbnail_and_page_render(auth_client, tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    pdf = make_pdf_bytes()
    _, _, attachment = await _upload(
        auth_client, file_bytes=pdf, mime="application/pdf", filename="report.pdf"
    )

    thumb = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/webp"

    page0 = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/pages/0")
    assert page0.status_code == 200
    assert page0.headers["content-type"] == "image/png"
    assert page0.content[:8] == b"\x89PNG\r\n\x1a\n"

    page1 = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/pages/1")
    assert page1.status_code == 200

    out_of_range = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/pages/5")
    assert out_of_range.status_code == 404


async def test_page_render_rejected_for_image(auth_client, tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    _, _, attachment = await _upload(auth_client)
    resp = await auth_client.get(f"/api/v1/attachments/{attachment['id']}/pages/0")
    assert resp.status_code == 400


async def test_scoped_across_households(client, tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    await client.post(
        "/api/v1/auth/register", json={"username": "thumb_a", "password": "Password1!"}
    )
    _, _, attachment = await _upload(client, member_name="OwnerMember")
    await client.post(
        "/api/v1/auth/register", json={"username": "thumb_b", "password": "Password1!"}
    )
    resp = await client.get(f"/api/v1/attachments/{attachment['id']}/thumbnail")
    assert resp.status_code == 404
