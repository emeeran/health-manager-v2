"""Content-addressable storage: validation, encryption at rest, dedup."""

import hashlib

import pytest
from fastapi import HTTPException

from app.core import storage
from app.core.encryption import decrypt_bytes


PDF_BYTES = b"%PDF-1.4 fake pdf content for testing"


def test_save_bytes_writes_sharded_encrypted_path(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    stored = storage.save_bytes(PDF_BYTES, "application/pdf")

    assert stored.content_hash == hashlib.sha256(PDF_BYTES).hexdigest()
    rel = stored.rel_path
    assert rel.startswith(f"files/{stored.content_hash[:2]}/{stored.content_hash}")
    assert rel.endswith(".pdf")

    on_disk = (tmp_path / rel).read_bytes()
    assert PDF_BYTES not in on_disk  # encrypted at rest
    assert decrypt_bytes(on_disk) == PDF_BYTES


def test_dedup_same_content_shares_file(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    first = storage.save_bytes(PDF_BYTES, "application/pdf")
    second = storage.save_bytes(PDF_BYTES, "application/pdf")
    assert first.rel_path == second.rel_path
    assert first.content_hash == second.content_hash


def test_rejects_non_pdf_mime_claiming_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    with pytest.raises(HTTPException) as exc:
        storage.save_bytes(b"not a pdf at all", "application/pdf")
    assert exc.value.status_code == 415


def test_rejects_disallowed_mime(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    with pytest.raises(HTTPException) as exc:
        storage.save_bytes(b"#!/bin/sh\nrm -rf /", "text/x-shellscript")
    assert exc.value.status_code == 415


def test_magic_bytes_per_type(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    assert storage._magic_ok(b"\x89PNG\r\n\x1a\nrest", "image/png")
    assert storage._magic_ok(b"\xff\xd8\xffrest", "image/jpeg")
    assert storage._magic_ok(b"RIFF1234WEBPVP8", "image/webp")
    assert not storage._magic_ok(b"GIF89a", "image/png")


def test_read_plaintext_roundtrip_and_path_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "storage_root", lambda: tmp_path)
    stored = storage.save_bytes(PDF_BYTES, "application/pdf")
    assert storage.read_plaintext(stored.rel_path) == PDF_BYTES

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        storage.read_plaintext("../../etc/passwd")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        storage.read_plaintext(f"files/{'a' * 2}/{'b' * 64}.pdf")  # valid shape, missing file
    assert exc.value.status_code == 404
