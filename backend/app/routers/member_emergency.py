"""Emergency ICE card payload: everything a first responder needs, one call."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import (
    Allergy,
    ConditionEpisode,
    Medication,
    MedicationStatus,
    Provider,
    ProviderAssignment,
    User,
)
from app.schemas.people import EmergencyCard

router = APIRouter(prefix="/members/{member_id}/emergency", tags=["emergency"])


@router.get("", response_model=EmergencyCard)
async def emergency_card(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmergencyCard:
    member = await get_scoped_member(member_id, user, db)

    allergies = (
        await db.scalars(
            select(Allergy).where(Allergy.member_id == member_id).order_by(Allergy.severity.desc())
        )
    ).all()
    conditions = (
        await db.scalars(
            select(ConditionEpisode).where(
                ConditionEpisode.member_id == member_id,
                ConditionEpisode.status.in_(["active", "chronic"]),
            )
        )
    ).all()
    medications = (
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member_id,
                Medication.status == MedicationStatus.ACTIVE.value,
            )
        )
    ).all()
    provider_rows = (
        await db.execute(
            select(Provider, ProviderAssignment)
            .join(
                ProviderAssignment,
                ProviderAssignment.provider_id == Provider.id,
            )
            .where(ProviderAssignment.member_id == member_id)
        )
    ).all()

    return EmergencyCard(
        member={
            "name": member.name,
            "birth_date": member.birth_date.isoformat() if member.birth_date else None,
            "blood_group": member.blood_group,
            "phone": member.phone,
            "address": member.address,
            "emergency_contact_name": member.emergency_contact_name,
            "emergency_contact_phone": member.emergency_contact_phone,
            "medical_history": member.medical_history,
        },
        allergies=[
            {
                "substance": a.substance,
                "severity": a.severity,
                "reaction": a.reaction,
            }
            for a in allergies
        ],
        conditions=[{"name": c.name, "status": c.status} for c in conditions],
        active_medications=[{"medicine": m.medicine, "dosage": m.dosage} for m in medications],
        providers=[
            {
                "name": provider.name,
                "specialty": provider.specialty,
                "hospital": provider.hospital,
                "uhid": assignment.uhid,
            }
            for provider, assignment in provider_rows
        ],
    )
