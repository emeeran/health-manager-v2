"""Vaccination CRUD."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.models.vaccination import Vaccination
from app.schemas.vaccination import (
    VaccinationCreate,
    VaccinationResponse,
    VaccinationUpdate,
)

router = APIRouter(prefix="/members/{member_id}/vaccinations", tags=["vaccinations"])


async def _get_vaccination_or_404(
    member_id: uuid.UUID, vaccination_id: uuid.UUID, db: AsyncSession
) -> Vaccination:
    vaccination = await db.get(Vaccination, vaccination_id)
    if vaccination is None or vaccination.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaccination not found")
    return vaccination


@router.get("", response_model=list[VaccinationResponse])
async def list_vaccinations(
    member_id: uuid.UUID,
    limit: int = Query(default=200, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Vaccination]:
    """List all vaccinations for a member, most recent first."""
    await get_scoped_member(member_id, user, db)
    rows = await db.scalars(
        select(Vaccination)
        .where(Vaccination.member_id == member_id)
        .order_by(Vaccination.date_administered.desc())
        .limit(limit)
    )
    return list(rows)


@router.post("", response_model=VaccinationResponse, status_code=status.HTTP_201_CREATED)
async def create_vaccination(
    member_id: uuid.UUID,
    body: VaccinationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Vaccination:
    """Add a vaccination record."""
    await get_scoped_member(member_id, user, db)
    vaccination = Vaccination(member_id=member_id, **body.model_dump())
    db.add(vaccination)
    await db.flush()
    await db.refresh(vaccination)
    return vaccination


@router.patch("/{vaccination_id}", response_model=VaccinationResponse)
async def update_vaccination(
    member_id: uuid.UUID,
    vaccination_id: uuid.UUID,
    body: VaccinationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Vaccination:
    """Update a vaccination record."""
    await get_scoped_member(member_id, user, db)
    vaccination = await _get_vaccination_or_404(member_id, vaccination_id, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(vaccination, key, value)
    await db.flush()
    await db.refresh(vaccination)
    return vaccination


@router.delete("/{vaccination_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vaccination(
    member_id: uuid.UUID,
    vaccination_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a vaccination record."""
    await get_scoped_member(member_id, user, db)
    vaccination = await _get_vaccination_or_404(member_id, vaccination_id, db)
    await db.delete(vaccination)
    await db.flush()
