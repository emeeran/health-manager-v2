"""Medicine catalog crawler (1mg / Apollo pharmacy) toggle + batch runner.

The crawler itself is ``backend/tools/crawl.py`` — a standalone, checkpointed
SQLite crawler that pulls a bounded batch of drug pages per invocation. This
service stores the runtime on/off toggle (Settings UI, admin-guarded, audited)
as an app_secrets row so it survives restarts, falling back to the
MEDICINE_CRAWLER_ENABLED env default when unset, and shells the crawler out in
batches so a scheduler tick never runs unbounded.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import AppSecret

logger = logging.getLogger(__name__)

TOGGLE_KEY = "MEDICINE_CRAWLER_ENABLED"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "tools" / "crawl.py"


async def is_enabled(db: AsyncSession) -> bool:
    """Stored toggle beats the env/config default (same precedence as keys)."""
    row = await db.get(AppSecret, TOGGLE_KEY)
    if row is not None:
        return decrypt_secret(row.value_encrypted) == "true"
    return get_settings().MEDICINE_CRAWLER_ENABLED


async def set_enabled(db: AsyncSession, enabled: bool) -> None:
    row = await db.get(AppSecret, TOGGLE_KEY)
    encrypted = encrypt_secret("true" if enabled else "false")
    if row is None:
        row = AppSecret(key=TOGGLE_KEY, value_encrypted=encrypted or "")
    else:
        row.value_encrypted = encrypted or ""
    db.add(row)


async def get_status(db: AsyncSession) -> dict:
    settings = get_settings()
    row = await db.get(AppSecret, TOGGLE_KEY)
    stored = row is not None
    enabled = await is_enabled(db)
    return {
        "enabled": enabled,
        "source": "db" if stored else "default",
        "batch_pages": settings.MEDICINE_CRAWLER_BATCH_PAGES,
        "data_dir": settings.MEDICINE_CRAWLER_DATA_DIR,
        "script_present": SCRIPT_PATH.is_file(),
    }


async def run_batch(limit: int, data_dir: str, timeout_seconds: int) -> dict:
    """Crawl one bounded batch and refresh the CSV export.

    Returns a small summary dict; never raises for crawler-side failures
    (they come back as status=error/timeout with a stdout tail for the log).
    """
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "crawl",
        "--site", "all",
        "--limit", str(limit),
        "--workers", "6",
        "--delay", "0.4",
        "--export",
        "--data", data_dir,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        logger.error("medicine crawler could not start: %s", exc)
        return {"status": "error", "detail": str(exc)[:200]}

    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("medicine crawler batch exceeded %ss — killed", timeout_seconds)
        return {"status": "timeout", "detail": f"exceeded {timeout_seconds}s"}

    lines = (out or b"").decode(errors="replace").strip().splitlines()
    last = lines[-1].strip() if lines else ""
    if last.startswith("RESULT "):
        try:
            summary = json.loads(last[len("RESULT "):])
            summary["status"] = "ok"
            return summary
        except json.JSONDecodeError:
            pass
    if proc.returncode != 0:
        return {"status": "error", "detail": last[:200] or f"exit {proc.returncode}"}
    return {"status": "ok", "detail": last[:200]}
