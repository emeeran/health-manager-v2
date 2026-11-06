"""Apple Health import router (Phase 10).

POST /api/v1/members/{member_id}/import/apple-health — multipart Export.xml
→ VitalMeasurement daily rows (idempotent upsert) + created/updated summary.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.services.health_import_service import (
    MAX_EXPORT_BYTES,
    aggregate_health_xml,
    apply_health_import,
)

router = APIRouter(prefix="/members/{member_id}/import", tags=["health-import"])
logger = logging.getLogger(__name__)


@router.post("/apple-health")
async def import_apple_health(
    member_id: uuid.UUID,
    file: UploadFile,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest an Apple Health Export.xml into the member's vitals (idempotent)."""
    await get_scoped_member(member_id, user, db)

    data = await file.read()
    if len(data) > MAX_EXPORT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Export too large (300 MB limit)"
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty upload")
    try:
        aggregated = aggregate_health_xml(data)
    except Exception as exc:
        logger.warning("Health export parse failed: %s", exc)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Not a readable Apple Health Export.xml",
        ) from exc

    result = await apply_health_import(db, member_id, aggregated)
    result["skipped_types"] = aggregated["skipped_types"]
    await db.flush()
    return result
