"""Backup endpoints: create, list, download, restore request, schedule."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_membership, require_household_admin
from app.models import Household, User
from app.services import backup_service
from app.services.audit import record_audit
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/backup", tags=["backup"])


class RestoreRequest(BaseModel):
    filename: str


class ScheduleUpdate(BaseModel):
    schedule: Literal["off", "daily", "weekly"]


def _settings_dict(household: Household) -> dict:
    """settings_json parsed, preserving unknown keys (ai-config lives here too)."""
    if not household.settings_json:
        return {}
    try:
        parsed = json.loads(household.settings_json)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.post("/create")
async def create_backup(_: User = Depends(get_current_user)) -> dict:
    path = backup_service.create_backup()
    return {"filename": path.name, "size_bytes": path.stat().st_size}


@router.get("/list")
async def list_backups(_: User = Depends(get_current_user)) -> list[dict]:
    return backup_service.list_backups()


@router.get("/download/{filename}")
async def download_backup(filename: str, _: User = Depends(get_current_user)) -> Response:
    try:
        data = backup_service.read_backup(filename)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found") from exc
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/schedule")
async def get_backup_schedule(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = await get_household_membership(user, db)
    settings = _settings_dict(household)
    schedule = settings.get("backup_schedule", "daily")
    if schedule not in ("off", "daily", "weekly"):
        schedule = "daily"
    return {"schedule": schedule}


@router.put("/schedule")
async def put_backup_schedule(
    body: ScheduleUpdate,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Store the schedule on the household's settings_json alongside (not
    clobbering) the ai-config keys — see jobs.get_backup_schedule."""
    household, _ = result
    settings = _settings_dict(household)
    settings["backup_schedule"] = body.schedule
    household.settings_json = json.dumps(settings)
    record_audit(
        db,
        action="household.backup_schedule",
        household_id=household.id,
        detail=body.schedule,
        ip=request.client.host if request.client else None,
    )
    await db.flush()
    return {"schedule": body.schedule}


@router.post("/restore-request", status_code=status.HTTP_202_ACCEPTED)
async def restore_request(body: RestoreRequest, _: User = Depends(get_current_user)) -> dict:
    """Queue a privileged restore — the root pipeline takes over and the
    app restarts on the restored data."""
    try:
        backup_service.request_restore(body.filename)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found") from exc
    return {"message": "Restore queued. The system service will restart the app."}
