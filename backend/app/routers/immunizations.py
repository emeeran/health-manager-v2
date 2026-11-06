"""Immunizations + milestones router.

GET  /members/{id}/immunizations/schedule   UIP schedule + catch-up plan
GET  /members/{id}/milestones               checklist + expected status
PUT  /members/{id}/milestones/{key}         record/clear an achievement
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import FamilyMember, User
from app.models.milestone import MilestoneAchievement
from app.models.vaccination import Vaccination
from app.services.immunization_service import (
    MILESTONES,
    age_months_on,
    build_schedule,
    milestones_for_age,
)

router = APIRouter(prefix="/members/{member_id}", tags=["immunizations"])


@router.get("/immunizations/schedule")
async def get_immunization_schedule(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The UIP schedule with catch-up dates and per-dose status."""
    member: FamilyMember = await get_scoped_member(member_id, user, db)
    if member.birth_date is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Child's date of birth is required"
        )
    vaccinations = (
        await db.execute(
            select(Vaccination.name, Vaccination.date_administered).where(
                Vaccination.member_id == member_id
            )
        )
    ).all()
    pairs = [(name, when or date.today()) for name, when in vaccinations]
    return build_schedule(member.birth_date, pairs)


@router.get("/milestones")
async def get_milestones(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The milestone checklist with expected status + the child's record."""
    member: FamilyMember = await get_scoped_member(member_id, user, db)
    age_months = age_months_on(member.birth_date, date.today()) if member.birth_date else None
    definitions = (
        milestones_for_age(age_months) if age_months is not None else [dict(m) for m in MILESTONES]
    )
    achieved = {
        (row.milestone_key, row.achieved_on.isoformat() if row.achieved_on else None)
        for row in (
            await db.scalars(
                select(MilestoneAchievement).where(MilestoneAchievement.member_id == member_id)
            )
        )
    }
    by_key = {k: v for k, v in achieved}
    rows = [
        {
            **definition,
            "achieved": definition["key"] in by_key,
            "achieved_on": by_key.get(definition["key"]),
        }
        for definition in definitions
    ]
    return {
        "age_months": round(age_months, 1) if age_months is not None else None,
        "rows": rows,
    }


class MilestoneSet(BaseModel):
    achieved: bool
    achieved_on: date | None = None


@router.put("/milestones/{milestone_key}")
async def set_milestone(
    member_id: uuid.UUID,
    milestone_key: str,
    body: MilestoneSet,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_scoped_member(member_id, user, db)
    if milestone_key not in {m["key"] for m in MILESTONES}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown milestone")
    existing = await db.scalar(
        select(MilestoneAchievement)
        .where(MilestoneAchievement.member_id == member_id)
        .where(MilestoneAchievement.milestone_key == milestone_key)
    )
    if body.achieved:
        if existing is None:
            existing = MilestoneAchievement(member_id=member_id, milestone_key=milestone_key)
            db.add(existing)
        existing.achieved_on = body.achieved_on or date.today()
    elif existing is not None:
        await db.delete(existing)
    await db.flush()
    return {"key": milestone_key, "achieved": body.achieved}
