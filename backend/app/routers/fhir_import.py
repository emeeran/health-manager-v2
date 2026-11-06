"""FHIR bundle import router (Phase 10).

POST /api/v1/members/{member_id}/import/fhir — raw FHIR R4 Bundle JSON body
→ mapped domain rows (idempotent) + per-type created/skipped summary.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.services.fhir_import_service import (
    MAX_BUNDLE_BYTES,
    apply_staged,
    parse_bundle,
    stage_bundle,
)

router = APIRouter(prefix="/members/{member_id}/import", tags=["fhir-import"])
logger = logging.getLogger(__name__)


@router.post("/fhir")
async def import_fhir(
    member_id: uuid.UUID,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Import a FHIR R4 Bundle into the member's record set (idempotent)."""
    await get_scoped_member(member_id, user, db)

    body = await request.body()
    if len(body) > MAX_BUNDLE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Bundle too large (20 MB limit)"
        )
    try:
        bundle = parse_bundle(body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    staged = stage_bundle(bundle)
    summary = await apply_staged(db, member_id, staged)
    await db.flush()
    logger.info(
        "FHIR import for member %s: created=%s skipped_existing=%s",
        member_id,
        summary["created"],
        summary["skipped_existing"],
    )
    return summary
