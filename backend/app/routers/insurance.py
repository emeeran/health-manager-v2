"""Insurance policies and claims, scoped through the member's household."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import InsuranceClaim, InsurancePolicy, User
from app.schemas.people import (
    ClaimCreate,
    ClaimResponse,
    ClaimUpdate,
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
)

router = APIRouter(prefix="/members/{member_id}/insurance", tags=["insurance"])


async def _scoped_policy(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> InsurancePolicy:
    await get_scoped_member(member_id, user, db)
    policy = await db.get(InsurancePolicy, policy_id)
    if policy is None or policy.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")
    return policy


@router.get("/policies", response_model=list[PolicyResponse])
async def list_policies(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InsurancePolicy]:
    await get_scoped_member(member_id, user, db)
    rows = await db.scalars(
        select(InsurancePolicy)
        .where(InsurancePolicy.member_id == member_id)
        .order_by(InsurancePolicy.created_at.desc())
    )
    return list(rows)


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    member_id: uuid.UUID,
    body: PolicyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InsurancePolicy:
    await get_scoped_member(member_id, user, db)
    policy = InsurancePolicy(member_id=member_id, **body.model_dump())
    db.add(policy)
    await db.flush()
    return policy


@router.patch("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InsurancePolicy:
    policy = await _scoped_policy(member_id, policy_id, user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)
    await db.flush()
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    policy = await _scoped_policy(member_id, policy_id, user, db)
    await db.delete(policy)
    await db.flush()


@router.get("/policies/{policy_id}/claims", response_model=list[ClaimResponse])
async def list_claims(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InsuranceClaim]:
    await _scoped_policy(member_id, policy_id, user, db)
    rows = await db.scalars(
        select(InsuranceClaim)
        .where(InsuranceClaim.policy_id == policy_id)
        .order_by(InsuranceClaim.claimed_on.desc())
    )
    return list(rows)


@router.post(
    "/policies/{policy_id}/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_claim(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    body: ClaimCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InsuranceClaim:
    await _scoped_policy(member_id, policy_id, user, db)
    claim = InsuranceClaim(policy_id=policy_id, **body.model_dump())
    db.add(claim)
    await db.flush()
    return claim


async def _scoped_claim(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    claim_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> InsuranceClaim:
    await _scoped_policy(member_id, policy_id, user, db)
    claim = await db.get(InsuranceClaim, claim_id)
    if claim is None or claim.policy_id != policy_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    return claim


@router.patch("/policies/{policy_id}/claims/{claim_id}", response_model=ClaimResponse)
async def update_claim(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    claim_id: uuid.UUID,
    body: ClaimUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InsuranceClaim:
    claim = await _scoped_claim(member_id, policy_id, claim_id, user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(claim, field, value.value if hasattr(value, "value") else value)
    await db.flush()
    return claim


@router.delete("/policies/{policy_id}/claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_claim(
    member_id: uuid.UUID,
    policy_id: uuid.UUID,
    claim_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    claim = await _scoped_claim(member_id, policy_id, claim_id, user, db)
    await db.delete(claim)
    await db.flush()
