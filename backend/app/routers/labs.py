"""Lab result CRUD."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import LabResult, User
from app.schemas.lab import LabCreate, LabResponse

router = APIRouter(prefix="/members/{member_id}/labs", tags=["labs"])


@router.get("", response_model=list[LabResponse])
async def list_labs(
    member_id: uuid.UUID,
    limit: int = Query(default=200, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LabResult]:
    await get_scoped_member(member_id, user, db)
    rows = await db.scalars(
        select(LabResult)
        .where(LabResult.member_id == member_id)
        .order_by(LabResult.record_date.desc().nullslast(), LabResult.created_at.desc())
        .limit(limit)
    )
    return list(rows)


@router.post("", response_model=LabResponse, status_code=status.HTTP_201_CREATED)
async def create_lab(
    member_id: uuid.UUID,
    body: LabCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LabResult:
    await get_scoped_member(member_id, user, db)
    lab = LabResult(member_id=member_id, **body.model_dump())
    db.add(lab)
    await db.flush()
    await db.refresh(lab)
    return lab


@router.delete("/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lab(
    member_id: uuid.UUID,
    lab_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_scoped_member(member_id, user, db)
    lab = await db.get(LabResult, lab_id)
    if lab is None or lab.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab not found")
    await db.delete(lab)
    await db.flush()
