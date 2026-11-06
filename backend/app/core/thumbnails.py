"""Thumbnails and PDF page rendering.

Thumbnails are content-addressed (`thumbnails/<content_hash>.webp`, 300px,
quality 80) and generated lazily on first request — the store already has
the plaintext bytes, so the request path can afford a one-off ~100ms
render; subsequent requests are a plain file serve.

PDF page rendering powers page-by-page preview without downloading the
whole document to the client.
"""

import asyncio
import io
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import HTTPException, status
from PIL import Image

from app.core import storage

THUMBNAIL_SIZE = 300
PAGE_RENDER_DPI = 96


def _thumbnails_dir() -> Path:
    # Via the module so test patches of storage.storage_root apply here too.
    d = storage.storage_root() / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _image_to_webp_bytes(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=80)
    return buf.getvalue()


def _pdf_thumbnail_bytes(data: bytes) -> bytes:
    with fitz.open(stream=data, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(dpi=PAGE_RENDER_DPI)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
    return _image_to_webp_bytes(img)


def thumbnail_path_for(content_hash: str) -> Path:
    return _thumbnails_dir() / f"{content_hash}.webp"


def _generate_thumbnail(content_hash: str, file_path: str) -> bytes:
    cached = thumbnail_path_for(content_hash)
    if cached.exists():
        return cached.read_bytes()
    data = storage.read_plaintext(file_path)
    if file_path.endswith(".pdf"):
        thumb = _pdf_thumbnail_bytes(data)
    else:
        thumb = _image_to_webp_bytes(Image.open(io.BytesIO(data)))
    # Write-then-rename so concurrent requests never serve a partial file.
    tmp = cached.with_suffix(".tmp")
    tmp.write_bytes(thumb)
    tmp.replace(cached)
    return thumb


async def get_or_create_thumbnail(content_hash: str, file_path: str) -> bytes:
    return await asyncio.to_thread(_generate_thumbnail, content_hash, file_path)


def render_pdf_page(data: bytes, page_number: int) -> bytes:
    """Render a 0-based PDF page to PNG bytes."""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if page_number < 0 or page_number >= doc.page_count:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    f"Page {page_number} out of range (0..{doc.page_count - 1})",
                )
            pix = doc[page_number].get_pixmap(dpi=PAGE_RENDER_DPI)
            png: bytes = pix.tobytes("png")
            return png
    except fitz.FileDataError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a readable PDF") from exc
