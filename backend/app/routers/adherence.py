"""Today's dose schedule for a member (expand_day over active medications).

Pill tracking (logging/history) was removed — this is a read-only view of
what is scheduled today, feeding the medicine schedule card.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import Medication, User
from app.schemas.adherence import AdherenceTodayResponse, DoseView, PrnView
from app.services import dosing

router = APIRouter(prefix="/members/{member_id}/adherence", tags=["adherence"])


@router.get("/today", response_model=AdherenceTodayResponse)
async def adherence_today(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdherenceTodayResponse:
    await get_scoped_member(member_id, user, db)
    today = date.today()
    meds = (
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member_id, Medication.status == "active"
            )
        )
    ).all()

    doses: list[DoseView] = []
    prn: list[PrnView] = []
    for med in meds:
        if med.schedule_type == "prn":
            prn.append(PrnView(medication_id=med.id, medicine=med.medicine, dosage=med.dosage))
            continue
        for dose in dosing.expand_day(med, today):
            doses.append(
                DoseView(
                    medication_id=med.id,
                    medicine=med.medicine,
                    dosage=med.dosage,
                    slot=dose.slot,
                    dose_count=dose.dose_count,
                    scheduled_time=dose.scheduled_time,
                    annotation=dose.annotation,
                )
            )
    return AdherenceTodayResponse(date=today, doses=doses, prn=prn)
