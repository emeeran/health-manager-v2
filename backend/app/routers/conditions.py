"""Condition episodes CRUD + record/medication linking (problem list)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import HealthRecord, Medication, User
from app.models.condition import ConditionEpisode, ConditionStatus
from app.schemas.condition import ConditionCreate, ConditionResponse, ConditionUpdate

router = APIRouter(prefix="/members/{member_id}/conditions", tags=["conditions"])


async def _get_condition_or_404(
    member_id: uuid.UUID, condition_id: uuid.UUID, db: AsyncSession
) -> ConditionEpisode:
    condition = await db.get(ConditionEpisode, condition_id)
    if condition is None or condition.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Condition not found")
    return condition


async def _counts(
    db: AsyncSession, member_id: uuid.UUID, condition_id: uuid.UUID
) -> tuple[int, int]:
    records = await db.scalar(
        select(func.count())
        .select_from(HealthRecord)
        .where(
            HealthRecord.condition_id == condition_id,
            HealthRecord.member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )
    )
    medications = await db.scalar(
        select(func.count())
        .select_from(Medication)
        .where(
            Medication.condition_id == condition_id,
            Medication.member_id == member_id,
        )
    )
    return int(records or 0), int(medications or 0)


async def _to_response(db: AsyncSession, condition: ConditionEpisode) -> ConditionResponse:
    record_count, medication_count = await _counts(db, condition.member_id, condition.id)
    body = ConditionResponse.model_validate(condition)
    body.record_count = record_count
    body.medication_count = medication_count
    return body


def _validate_course(condition: ConditionEpisode) -> None:
    """Episode-course invariants, enforced on every write."""
    if (
        condition.resolution_date
        and condition.onset_date
        and condition.resolution_date < condition.onset_date
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "resolution_date cannot precede onset_date",
        )
    if condition.status == ConditionStatus.RESOLVED and not condition.resolution_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "resolved conditions require a resolution_date",
        )


@router.get("", response_model=list[ConditionResponse])
async def list_conditions(
    member_id: uuid.UUID,
    condition_status: ConditionStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConditionResponse]:
    """List a member's problem list, newest episode first."""
    await get_scoped_member(member_id, user, db)
    stmt = (
        select(ConditionEpisode)
        .where(ConditionEpisode.member_id == member_id)
        .order_by(ConditionEpisode.created_at.desc())
    )
    if condition_status:
        stmt = stmt.where(ConditionEpisode.status == condition_status.value)
    rows = await db.scalars(stmt)
    return [await _to_response(db, c) for c in rows]


@router.post("", response_model=ConditionResponse, status_code=status.HTTP_201_CREATED)
async def create_condition(
    member_id: uuid.UUID,
    body: ConditionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConditionResponse:
    """Add an episode to the member's problem list."""
    await get_scoped_member(member_id, user, db)
    condition = ConditionEpisode(
        member_id=member_id,
        name=body.name,
        icd10_code=body.icd10_code,
        status=body.status.value,
        onset_date=body.onset_date,
        resolution_date=body.resolution_date,
        notes=body.notes,
    )
    _validate_course(condition)
    db.add(condition)
    await db.flush()
    await db.refresh(condition)
    return await _to_response(db, condition)


@router.get("/{condition_id}", response_model=ConditionResponse)
async def get_condition(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConditionResponse:
    """Fetch one episode with linked-entity counts."""
    await get_scoped_member(member_id, user, db)
    condition = await _get_condition_or_404(member_id, condition_id, db)
    return await _to_response(db, condition)


@router.patch("/{condition_id}", response_model=ConditionResponse)
async def update_condition(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    body: ConditionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConditionResponse:
    """Update an episode (partial); course invariants hold after the merge."""
    await get_scoped_member(member_id, user, db)
    condition = await _get_condition_or_404(member_id, condition_id, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(condition, key, value.value if hasattr(value, "value") else value)
    _validate_course(condition)
    await db.flush()
    await db.refresh(condition)
    return await _to_response(db, condition)


@router.delete("/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_condition(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an episode; linked records/medications survive (SET NULL)."""
    await get_scoped_member(member_id, user, db)
    condition = await _get_condition_or_404(member_id, condition_id, db)
    await db.delete(condition)
    await db.flush()


# --- record & medication linking ---------------------------------------------


async def _link(condition_id: uuid.UUID, target, db: AsyncSession) -> None:
    if target.condition_id == condition_id:
        return  # idempotent re-link
    target.condition_id = condition_id
    await db.flush()


async def _get_linked_record(
    member_id: uuid.UUID, record_id: uuid.UUID, db: AsyncSession
) -> HealthRecord:
    record = await db.get(HealthRecord, record_id)
    if record is None or record.member_id != member_id or record.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    return record


async def _get_linked_medication(
    member_id: uuid.UUID, medication_id: uuid.UUID, db: AsyncSession
) -> Medication:
    medication = await db.get(Medication, medication_id)
    if medication is None or medication.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medication not found")
    return medication


@router.post("/{condition_id}/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_record(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Attach a record to an episode."""
    await get_scoped_member(member_id, user, db)
    await _get_condition_or_404(member_id, condition_id, db)
    record = await _get_linked_record(member_id, record_id, db)
    await _link(condition_id, record, db)


@router.delete("/{condition_id}/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_record(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Detach a record from an episode."""
    await get_scoped_member(member_id, user, db)
    record = await _get_linked_record(member_id, record_id, db)
    if record.condition_id != condition_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record is not linked to this condition")
    record.condition_id = None
    await db.flush()


@router.post("/{condition_id}/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_medication(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    medication_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Attach a medication to an episode."""
    await get_scoped_member(member_id, user, db)
    await _get_condition_or_404(member_id, condition_id, db)
    medication = await _get_linked_medication(member_id, medication_id, db)
    await _link(condition_id, medication, db)


@router.delete(
    "/{condition_id}/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def unlink_medication(
    member_id: uuid.UUID,
    condition_id: uuid.UUID,
    medication_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Detach a medication from an episode."""
    await get_scoped_member(member_id, user, db)
    medication = await _get_linked_medication(member_id, medication_id, db)
    if medication.condition_id != condition_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medication is not linked to this condition")
    medication.condition_id = None
    await db.flush()
