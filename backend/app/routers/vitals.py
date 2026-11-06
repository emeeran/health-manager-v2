"""Vitals time-series CRUD + reference ranges."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User, VitalMeasurement
from app.schemas.vital import VitalCreate, VitalResponse

router = APIRouter(prefix="/members/{member_id}/vitals", tags=["vitals"])


@router.get("", response_model=list[VitalResponse])
async def list_vitals(
    member_id: uuid.UUID,
    vital_type: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=500, le=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VitalMeasurement]:
    await get_scoped_member(member_id, user, db)
    conditions = [VitalMeasurement.member_id == member_id]
    if vital_type:
        conditions.append(VitalMeasurement.vital_type == vital_type)
    if since:
        conditions.append(VitalMeasurement.measured_at >= since)
    rows = await db.scalars(
        select(VitalMeasurement)
        .where(*conditions)
        .order_by(VitalMeasurement.measured_at.desc())
        .limit(limit)
    )
    return list(rows)


@router.post("", response_model=VitalResponse, status_code=status.HTTP_201_CREATED)
async def create_vital(
    member_id: uuid.UUID,
    body: VitalCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VitalMeasurement:
    await get_scoped_member(member_id, user, db)
    vital = VitalMeasurement(
        member_id=member_id,
        vital_type=body.vital_type.value,
        value_num=body.value_num,
        value_secondary=body.value_secondary,
        unit=body.unit,
        glucose_context=body.glucose_context.value if body.glucose_context else None,
        measured_at=body.measured_at,
        source=body.source,
    )
    db.add(vital)
    await db.flush()
    await db.refresh(vital)
    return vital


async def _get_vital_scoped(
    member_id: uuid.UUID, vital_id: uuid.UUID, user: User, db: AsyncSession
) -> VitalMeasurement:
    await get_scoped_member(member_id, user, db)
    vital = await db.get(VitalMeasurement, vital_id)
    if vital is None or vital.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vital not found")
    return vital


@router.delete("/{vital_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vital(
    member_id: uuid.UUID,
    vital_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    vital = await _get_vital_scoped(member_id, vital_id, user, db)
    await db.delete(vital)
    await db.flush()
