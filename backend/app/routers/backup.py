"""Backup endpoints: create, list, download, restore request."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models import User
from app.services import backup_service

router = APIRouter(prefix="/backup", tags=["backup"])


class RestoreRequest(BaseModel):
    filename: str


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
