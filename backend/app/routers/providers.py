"""Provider directory (household-scoped) + per-member assignments (UHID)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id, get_scoped_member
from app.models import Provider, ProviderAssignment, User
from app.schemas.people import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
    ProviderCreate,
    ProviderResponse,
    ProviderUpdate,
)

router = APIRouter(prefix="/providers", tags=["providers"])
assignments = APIRouter(prefix="/members/{member_id}/providers", tags=["providers"])


async def _household_provider(provider_id: uuid.UUID, user: User, db: AsyncSession) -> Provider:
    provider = await db.get(Provider, provider_id)
    if provider is None or provider.household_id != await get_household_id(user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    return provider


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Provider]:
    household_id = await get_household_id(user, db)
    rows = await db.scalars(
        select(Provider).where(Provider.household_id == household_id).order_by(Provider.name)
    )
    return list(rows)


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Provider:
    provider = Provider(household_id=await get_household_id(user, db), **body.model_dump())
    db.add(provider)
    await db.flush()
    return provider


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Provider:
    return await _household_provider(provider_id, user, db)


@router.patch("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Provider:
    provider = await _household_provider(provider_id, user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(provider, field, value)
    await db.flush()
    return provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    provider = await _household_provider(provider_id, user, db)
    await db.delete(provider)
    await db.flush()


@assignments.get("", response_model=list[AssignmentResponse])
async def list_assignments(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssignmentResponse]:
    await get_scoped_member(member_id, user, db)
    rows = (
        await db.execute(
            select(ProviderAssignment, Provider)
            .join(Provider, Provider.id == ProviderAssignment.provider_id)
            .where(ProviderAssignment.member_id == member_id)
            .order_by(ProviderAssignment.created_at)
        )
    ).all()
    return [
        AssignmentResponse(
            id=assignment.id,
            provider_id=provider.id,
            provider_name=provider.name,
            specialty=provider.specialty,
            hospital=provider.hospital,
            uhid=assignment.uhid,
            created_at=assignment.created_at,
        )
        for assignment, provider in rows
    ]


@assignments.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def assign_provider(
    member_id: uuid.UUID,
    body: AssignmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    await get_scoped_member(member_id, user, db)
    provider = await _household_provider(body.provider_id, user, db)
    existing = await db.scalar(
        select(ProviderAssignment).where(
            ProviderAssignment.member_id == member_id,
            ProviderAssignment.provider_id == body.provider_id,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Provider already assigned to this member")
    assignment = ProviderAssignment(member_id=member_id, provider_id=provider.id, uhid=body.uhid)
    db.add(assignment)
    await db.flush()
    return AssignmentResponse(
        id=assignment.id,
        provider_id=provider.id,
        provider_name=provider.name,
        specialty=provider.specialty,
        hospital=provider.hospital,
        uhid=assignment.uhid,
        created_at=assignment.created_at,
    )


@assignments.patch("/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    member_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: AssignmentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    await get_scoped_member(member_id, user, db)
    assignment = await db.get(ProviderAssignment, assignment_id)
    if assignment is None or assignment.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    assignment.uhid = body.uhid
    provider = await db.get(Provider, assignment.provider_id)
    await db.flush()
    return AssignmentResponse(
        id=assignment.id,
        provider_id=assignment.provider_id,
        provider_name=provider.name if provider else "",
        specialty=provider.specialty if provider else None,
        hospital=provider.hospital if provider else None,
        uhid=assignment.uhid,
        created_at=assignment.created_at,
    )


@assignments.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_provider(
    member_id: uuid.UUID,
    assignment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_scoped_member(member_id, user, db)
    assignment = await db.get(ProviderAssignment, assignment_id)
    if assignment is None or assignment.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    await db.delete(assignment)
    await db.flush()
