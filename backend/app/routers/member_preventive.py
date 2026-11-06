"""Preventive-care recommendations (deterministic rules) + dismissals."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.services import preventive_care_service

router = APIRouter(prefix="/members/{member_id}/preventive", tags=["preventive-care"])

# Same bound as the rec_key column; keys are title slugs, never near this.
REC_KEY_MAX_LENGTH = 200


class DismissRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


@router.get("")
async def get_preventive_recommendations(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    member = await get_scoped_member(member_id, user, db)
    recommendations = await preventive_care_service.generate_recommendations(db, member)
    return {"recommendations": recommendations}


@router.post("/{rec_key}/dismiss")
async def dismiss_recommendation(
    member_id: uuid.UUID,
    rec_key: str = Path(max_length=REC_KEY_MAX_LENGTH),
    body: DismissRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await get_scoped_member(member_id, user, db)
    note = body.note.strip() if body and body.note else None
    return await preventive_care_service.dismiss(db, member_id, rec_key, note)


@router.delete("/{rec_key}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def undismiss_recommendation(
    member_id: uuid.UUID,
    rec_key: str = Path(max_length=REC_KEY_MAX_LENGTH),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_scoped_member(member_id, user, db)
    removed = await preventive_care_service.undismiss(db, member_id, rec_key)
    if not removed:
        raise HTTPException(404, "Recommendation was not dismissed")
