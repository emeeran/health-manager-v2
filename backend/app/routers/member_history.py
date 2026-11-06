"""Cross-domain member history: records, meds, labs, vitals in one feed."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import (
    HealthRecord,
    LabResult,
    Medication,
    User,
    VitalMeasurement,
)
from app.schemas.people import HistoryItem

router = APIRouter(prefix="/members/{member_id}/history", tags=["history"])


@router.get("", response_model=list[HistoryItem])
async def member_history(
    member_id: uuid.UUID,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HistoryItem]:
    """Chronological feed across domains, newest first.

    Each domain contributes its latest `limit` items and the merged feed is
    re-sorted and sliced — cheap at family scale, no UNION machinery.
    """
    await get_scoped_member(member_id, user, db)

    records = (
        await db.scalars(
            select(HealthRecord)
            .where(HealthRecord.member_id == member_id, HealthRecord.is_deleted.is_(False))
            .order_by(HealthRecord.record_date.desc())
            .limit(limit)
        )
    ).all()
    medications = (
        await db.scalars(
            select(Medication)
            .where(
                Medication.member_id == member_id,
                Medication.start_date.is_not(None),
            )
            .order_by(Medication.start_date.desc())
            .limit(limit)
        )
    ).all()
    labs = (
        await db.scalars(
            select(LabResult)
            .where(
                LabResult.member_id == member_id,
                LabResult.record_date.is_not(None),
            )
            .order_by(LabResult.record_date.desc())
            .limit(limit)
        )
    ).all()
    vitals = (
        await db.scalars(
            select(VitalMeasurement)
            .where(VitalMeasurement.member_id == member_id)
            .order_by(VitalMeasurement.measured_at.desc())
            .limit(limit)
        )
    ).all()

    items: list[HistoryItem] = []
    for record in records:
        items.append(
            HistoryItem(
                type="record",
                date=record.record_date,
                title=record.summary or record.diagnosis or record.record_type,
                detail=record.diagnosis,
                ref_id=record.id,
            )
        )
    for med in medications:
        items.append(
            HistoryItem(
                type="medication",
                date=med.start_date or date.today(),
                title=med.medicine,
                detail=med.dosage,
                ref_id=med.id,
            )
        )
    for lab in labs:
        detail = f"{lab.result or ''} {lab.units or ''}".strip() or None
        items.append(
            HistoryItem(
                type="lab",
                date=lab.record_date or date.today(),
                title=lab.test_name,
                detail=detail,
                ref_id=lab.id,
            )
        )
    for vital in vitals:
        title = f"{vital.vital_type.replace('_', ' ').title()}: {vital.value_num}"
        if vital.value_secondary is not None:
            title += f"/{vital.value_secondary}"
        if vital.unit:
            title += f" {vital.unit}"
        items.append(
            HistoryItem(
                type="vital",
                date=vital.measured_at.date(),
                title=title,
                detail=None,
                ref_id=vital.id,
            )
        )

    items.sort(key=lambda item: item.date, reverse=True)
    return items[offset : offset + limit]
