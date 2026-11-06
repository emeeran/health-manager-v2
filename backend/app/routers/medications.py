"""Medication CRUD with schedule types (daily/prn/taper/cycle)."""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import HealthRecord, Medication, User
from app.schemas.medication import (
    MedicationCreate,
    MedicationResponse,
    MedicationUpdate,
    to_response,
)
from app.models.medication import normalize_medicine_key
from app.schemas.medication import merge_schedule_update
from app.services.medication_service import new_medication

router = APIRouter(prefix="/members/{member_id}/medications", tags=["medications"])


@router.get("", response_model=list[MedicationResponse])
async def list_medications(
    member_id: uuid.UUID,
    med_status: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MedicationResponse]:
    await get_scoped_member(member_id, user, db)
    conditions = [Medication.member_id == member_id]
    if med_status:
        conditions.append(Medication.status == med_status)
    rows = await db.scalars(
        select(Medication).where(*conditions).order_by(Medication.created_at.desc()).limit(500)
    )
    return [to_response(m) for m in rows]


@router.post("", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
async def create_medication(
    member_id: uuid.UUID,
    body: MedicationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationResponse:
    await get_scoped_member(member_id, user, db)
    if body.record_id is not None:
        source = await db.get(HealthRecord, body.record_id)
        if source is None or source.member_id != member_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown record_id")
    try:
        med = new_medication(member_id, body)
    except (ValueError, PydanticValidationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.add(med)
    await db.flush()
    await db.refresh(med)
    return to_response(med)


async def _get_med_scoped(
    member_id: uuid.UUID, med_id: uuid.UUID, user: User, db: AsyncSession
) -> Medication:
    await get_scoped_member(member_id, user, db)
    med = await db.get(Medication, med_id)
    if med is None or med.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medication not found")
    return med


@router.patch("/{med_id}", response_model=MedicationResponse)
async def update_medication(
    member_id: uuid.UUID,
    med_id: uuid.UUID,
    body: MedicationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationResponse:
    med = await _get_med_scoped(member_id, med_id, user, db)
    updates = body.model_dump(exclude_unset=True)
    # slots/slot_times are schedule params, not columns — merge them into
    # schedule_json (keeping taper/cycle params) instead of setattr.
    slots = updates.pop("slots", None)
    slot_times = updates.pop("slot_times", None)
    if slots is not None or slot_times is not None:
        try:
            updates["schedule_json"] = merge_schedule_update(med.schedule_json, slots, slot_times)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if "medicine" in updates:
        med.medicine_key = normalize_medicine_key(updates["medicine"])
    for field, value in updates.items():
        setattr(med, field, value.value if hasattr(value, "value") else value)
    await db.flush()
    await db.refresh(med)
    return to_response(med)


@router.delete("/{med_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_medication(
    member_id: uuid.UUID,
    med_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    med = await _get_med_scoped(member_id, med_id, user, db)
    await db.delete(med)
    await db.flush()
