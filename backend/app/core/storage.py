"""Content-addressable file storage with encryption at rest.

- Allowed MIME: pdf/jpeg/png/webp, magic-byte verified (fail-closed).
- Dedup: SHA-256 of the PLAINTEXT → sharded path files/<h[:2]>/<hash>.<ext>.
  Identical content uploaded twice shares one file on disk.
- At rest the bytes are a Fernet token; the hash is of the plaintext, so
  dedup and integrity checks work despite encryption.
- Files are never deleted when an Attachment row is removed — they may be
  shared by other rows. Orphan GC is a later concern.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.encryption import decrypt_bytes, encrypt_bytes

ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class StoredFile:
    content_hash: str
    rel_path: str
    size: int
    mime: str
    ext: str


def _magic_ok(data: bytes, mime: str) -> bool:
    if mime == "application/pdf":
        return data[:5] == b"%PDF-"
    if mime == "image/jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if mime == "image/png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if mime == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def storage_root() -> Path:
    root = Path(get_settings().STORAGE_PATH)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def save_upload(upload: UploadFile) -> StoredFile:
    """Validate + persist an UploadFile into the store."""
    data = await upload.read()
    return save_bytes(data, upload.content_type or "application/octet-stream")


def validate_size(data: bytes) -> None:
    """413 when data exceeds MAX_FILE_SIZE_MB — shared with upload routers."""
    settings = get_settings()
    if len(data) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {settings.MAX_FILE_SIZE_MB} MB limit",
        )


def save_bytes(data: bytes, mime: str) -> StoredFile:
    validate_size(data)
    if mime not in ALLOWED_MIME:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported type: {mime}")
    if not _magic_ok(data, mime):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "File content does not match its type",
        )
    content_hash = hashlib.sha256(data).hexdigest()
    ext = ALLOWED_MIME[mime]
    rel_path = f"files/{content_hash[:2]}/{content_hash}{ext}"
    dest = storage_root() / rel_path
    if not dest.exists():  # dedup: only write if absent
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(encrypt_bytes(data))
    return StoredFile(
        content_hash=content_hash,
        rel_path=rel_path,
        size=len(data),
        mime=mime,
        ext=ext,
    )


def read_plaintext(rel_path: str) -> bytes:
    """Decrypt a stored file. Path is validated against the store layout."""
    if not re.fullmatch(r"files/[0-9a-f]{2}/[0-9a-f]{64}\.[a-z0-9]+", rel_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file path")
    path = storage_root() / rel_path
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from store")
    return decrypt_bytes(path.read_bytes())
