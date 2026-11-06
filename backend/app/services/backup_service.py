"""Backup: encrypted archive of health.db + attachments, restore handoff.

The archive is a gzipped tar of the SQLite file (online backup via the
sqlite3 backup API on a temp copy) plus the attachments tree, encrypted
with the same Fernet key as everything else.

Restore cannot safely swap the DB under a running app — the app writes a
request file (`.restore-request`) and the ROOT restore pipeline
(packaging/restore-archive.sh + systemd path unit) stops the services,
verifies the staged DB, swaps, and restarts. That privileged script is
exercised by its own test with env overrides.
"""

import io
import logging
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from cryptography.fernet import InvalidToken

from app.core.config import get_settings
from app.core.encryption import decrypt_bytes, encrypt_bytes
from app.core.storage import storage_root

BACKUPS_DIR = Path("data/backups")
RESTORE_REQUEST = Path("data/.restore-request")
ARCHIVE_NAME_PATTERN = r"^backup_\d{8}_\d{6}\.tar\.gz\.enc$"


def _sqlite_snapshot() -> bytes:
    """Consistent copy of the live DB via the sqlite3 backup API."""
    sqlite_path = get_settings().DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    src = sqlite3.connect(sqlite_path)
    dst = sqlite3.connect(tmp.name)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    data = Path(tmp.name).read_bytes()
    Path(tmp.name).unlink()
    return data


def create_backup() -> Path:
    """Write backups/backup_YYYYMMDD_HHMMSS.tar.gz.enc; return its path."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        db_bytes = _sqlite_snapshot()
        info = tarfile.TarInfo(name="health.db")
        info.size = len(db_bytes)
        tar.addfile(info, io.BytesIO(db_bytes))

        attachments = storage_root()
        for path in sorted(attachments.rglob("*")):
            if path.is_file():
                arcname = f"attachments/{path.relative_to(attachments)}"
                raw = path.read_bytes()
                info = tarfile.TarInfo(name=arcname)
                info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))

    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz.enc"
    dest = BACKUPS_DIR / filename
    dest.write_bytes(encrypt_bytes(buf.getvalue()))
    return dest


def list_backups() -> list[dict]:
    if not BACKUPS_DIR.exists():
        return []
    out = []
    for path in sorted(BACKUPS_DIR.glob("backup_*.tar.gz.enc"), reverse=True):
        out.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
        )
    return out


def read_backup(filename: str) -> bytes:
    """Decrypt+validate a backup archive name; return the tar bytes."""
    import re

    if not re.fullmatch(r"backup_\d{8}_\d{6}\.tar\.gz\.enc", filename):
        raise ValueError("Invalid backup filename")
    path = BACKUPS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return decrypt_bytes(path.read_bytes())


def validate_archive(tar_bytes: bytes) -> None:
    """Raise unless the tar contains an intact SQLite health.db."""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        names = tar.getnames()
        if "health.db" not in names:
            raise ValueError("Archive does not contain health.db")
        extracted = tar.extractfile("health.db")
        assert extracted is not None
        head = extracted.read(16)
        if not head.startswith(b"SQLite format 3\x00"):
            raise ValueError("health.db is not a SQLite database")


def request_restore(filename: str) -> None:
    """Write the request file consumed by the root restore pipeline."""
    import re

    if not re.fullmatch(r"backup_\d{8}_\d{6}\.tar\.gz\.enc", filename):
        raise ValueError("Invalid backup filename")
    path = BACKUPS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    RESTORE_REQUEST.parent.mkdir(parents=True, exist_ok=True)
    RESTORE_REQUEST.write_text(filename + "\n")


def decrypt_or_raise(data: bytes) -> bytes:
    try:
        return decrypt_bytes(data)
    except InvalidToken as exc:
        raise ValueError("Backup was encrypted with a different key") from exc


# ── Scheduler support (ops jobs) ────────────────────────────────────────

RETENTION_DAYS = 30
STATE_FILE = BACKUPS_DIR / ".backup_state.json"


def read_backup_state() -> dict[str, object]:
    """Load the persisted backup state (last_run/last_archive), or {}."""
    import json

    try:
        loaded = json.loads(STATE_FILE.read_text())
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        return {}


def write_backup_state(state: dict) -> None:
    """Persist the backup state; failures are logged, never raised."""
    import json

    try:
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except OSError:
        logging.getLogger(__name__).warning("Could not write backup state file")


def prune_old_archives(days: int = RETENTION_DAYS) -> int:
    """Delete backup archives older than *days* (mtime-based, 30-day retention).

    Idempotent: re-running over a pruned dir deletes nothing. Never touches
    the state file or restore-request marker.
    """
    import os
    import time

    if not BACKUPS_DIR.exists():
        return 0
    cutoff = time.time() - days * 86400
    deleted = 0
    for entry in os.scandir(BACKUPS_DIR):
        if entry.is_file() and entry.name.startswith("backup_") and entry.stat().st_mtime < cutoff:
            try:
                os.remove(entry.path)
                deleted += 1
            except OSError:
                logging.getLogger(__name__).warning("Could not delete old backup: %s", entry.path)
    return deleted


def extract_archive(tar_bytes: bytes, dest_dir: Path) -> list[Path]:
    """Extract a decrypted backup archive into *dest_dir* (created if needed).

    Members: ``health.db`` and ``attachments/...``. Used by the round-trip
    verification path; rejects absolute/traversing member names.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError(f"Unsafe archive member: {member.name}")
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            assert extracted is not None
            out = dest_dir / member.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(extracted.read())
            written.append(out)
    logging.getLogger(__name__).debug("Extracted %d archive members", len(written))
    return written


def restore_health_db(tar_bytes: bytes, dest_db: Path) -> Path:
    """Write the archived ``health.db`` out to *dest_db*; return its path.

    Caller validation is expected first (see ``validate_archive``).
    """
    for path in extract_archive(tar_bytes, dest_db.parent):
        if path.name == "health.db":
            if path != dest_db:
                path.rename(dest_db)
            return dest_db
    raise ValueError("Archive does not contain health.db")
