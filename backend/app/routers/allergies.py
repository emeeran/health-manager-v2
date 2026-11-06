"""Allergies CRUD + allergen–medication conflict endpoint."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import Allergy, User
from app.schemas.allergy import (
    AllergyConflict,
    AllergyCreate,
    AllergyResponse,
    AllergyUpdate,
)
from app.services.allergy_service import check_member_conflicts, list_for_member

router = APIRouter(prefix="/members/{member_id}/allergies", tags=["allergies"])


async def _get_allergy_or_404(
    member_id: uuid.UUID, allergy_id: uuid.UUID, db: AsyncSession
) -> Allergy:
    allergy = await db.get(Allergy, allergy_id)
    if allergy is None or allergy.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allergy not found")
    return allergy


@router.get("", response_model=list[AllergyResponse])
async def list_allergies(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Allergy]:
    """List all allergies for a member."""
    await get_scoped_member(member_id, user, db)
    return list(await list_for_member(db, member_id))


@router.post("", response_model=AllergyResponse, status_code=status.HTTP_201_CREATED)
async def create_allergy(
    member_id: uuid.UUID,
    body: AllergyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Allergy:
    """Add an allergy."""
    await get_scoped_member(member_id, user, db)
    allergy = Allergy(
        member_id=member_id,
        substance=body.substance.strip(),
        severity=body.severity,
        reaction=body.reaction,
        verified=body.verified,
    )
    db.add(allergy)
    await db.flush()
    await db.refresh(allergy)
    return allergy


@router.patch("/{allergy_id}", response_model=AllergyResponse)
async def update_allergy(
    member_id: uuid.UUID,
    allergy_id: uuid.UUID,
    body: AllergyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Allergy:
    """Update an allergy."""
    await get_scoped_member(member_id, user, db)
    allergy = await _get_allergy_or_404(member_id, allergy_id, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "substance" and value is not None:
            value = value.strip()
        setattr(allergy, key, value)
    await db.flush()
    await db.refresh(allergy)
    return allergy


@router.delete("/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allergy(
    member_id: uuid.UUID,
    allergy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an allergy."""
    await get_scoped_member(member_id, user, db)
    allergy = await _get_allergy_or_404(member_id, allergy_id, db)
    await db.delete(allergy)
    await db.flush()


# --- allergen–medication conflicts ------------------------------------------

conflicts_router = APIRouter(prefix="/members/{member_id}", tags=["allergies"])


@conflicts_router.get("/allergy-conflicts", response_model=list[AllergyConflict])
async def get_allergy_conflicts(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Flag active medications that match a known allergy (name match).

    Decision-support hints for clinician review, not certainties — matching
    is string-based on normalized names; cross-class matches (e.g. penicillin
    allergy vs amoxicillin) need a drug-class map and are not detected.
    """
    await get_scoped_member(member_id, user, db)
    return await check_member_conflicts(db, member_id)
