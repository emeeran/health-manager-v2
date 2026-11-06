"""Drug-information lookup for a single medicine (openFDA → RxNorm → AI)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.services import drug_info_service

router = APIRouter(prefix="/members/{member_id}/drug-info", tags=["drug-info"])


@router.get("")
async def get_drug_info(
    member_id: uuid.UUID,
    medicine: str = Query(..., description="Medicine name to look up"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not medicine.strip():
        raise HTTPException(422, "medicine query parameter is required")
    member = await get_scoped_member(member_id, user, db)
    return await drug_info_service.lookup_drug(
        medicine.strip(), local_only=not member.cloud_ai_consent
    )
