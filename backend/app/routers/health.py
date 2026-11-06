"""Health endpoints: liveness, readiness (DB + storage probe), and a
key-gated detail view for ops dashboards."""

import logging
import os

from fastapi import APIRouter, Header, Request, Response, status
from sqlalchemy import func, select, text

from app.core.database import engine

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(response: Response) -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _probe_storage()
        return {"status": "ready"}
    except Exception:
        logger.exception("readiness probe failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}


def _probe_storage() -> None:
    """Write+delete a probe file in the attachment store root. Raises on
    any I/O failure so /health/ready reports 503."""
    from app.core.storage import storage_root

    probe = storage_root() / ".healthprobe"
    probe.write_text("ok")
    probe.unlink()


def _health_key() -> str:
    """Ops key for /health/detail, read straight from the env — an unset
    key means detail is always 403."""
    return os.environ.get("HEALTH_KEY", "")


def _settings():
    from app.core.config import get_settings

    return get_settings()


@router.get("/detail")
async def detail(
    response: Response,
    request: Request,
    x_health_key: str | None = Header(default=None, alias="X-Health-Key"),
) -> dict:
    expected = _health_key()
    if not expected or x_health_key != expected:
        response.status_code = status.HTTP_403_FORBIDDEN
        return {"detail": "Not authorized to view health details"}
    try:
        return {
            "status": "ok",
            "app_env": _settings().APP_ENV,
            "rate_limit_backend": getattr(request.app.state, "rate_limit_backend", "memory"),
            "counts": await _counts(),
            "backups": _backup_summary(),
        }
    except Exception:
        logger.exception("health detail collection failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded"}


async def _counts() -> dict[str, int]:
    from app.core.database import SessionLocal
    from app.models import (
        Attachment,
        FamilyMember,
        HealthRecord,
        Medication,
        VitalMeasurement,
    )

    async with SessionLocal() as db:
        out: dict[str, int] = {}
        for name, model in (
            ("members", FamilyMember),
            ("records", HealthRecord),
            ("medications", Medication),
            ("vitals", VitalMeasurement),
            ("attachments", Attachment),
        ):
            out[name] = int(await db.scalar(select(func.count()).select_from(model)) or 0)
        return out


def _backup_summary() -> dict:
    from app.services.backup_service import list_backups, read_backup_state

    state = read_backup_state()
    return {
        "last_run": state.get("last_run"),
        "last_archive": state.get("last_archive"),
        "archive_count": len(list_backups()),
    }
