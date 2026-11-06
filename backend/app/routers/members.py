"""Family member CRUD, scoped to the caller's household."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id, get_scoped_member
from app.models import FamilyMember, Medication, User
from app.schemas.member import (
    MedicationMergeSuggestion,
    MemberCreate,
    MemberResponse,
    MemberUpdate,
)
from app.services.ai import router as ai_router

router = APIRouter(prefix="/members", tags=["members"])


async def _household_id(user: User, db: AsyncSession) -> uuid.UUID:
    return await get_household_id(user, db)


@router.get("", response_model=list[MemberResponse])
async def list_members(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[FamilyMember]:
    hid = await _household_id(user, db)
    rows = await db.scalars(
        select(FamilyMember)
        .where(FamilyMember.household_id == hid)
        .order_by(FamilyMember.created_at)
    )
    return list(rows)


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    body: MemberCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    hid = await _household_id(user, db)
    member = FamilyMember(household_id=hid, **body.model_dump())
    db.add(member)
    await db.flush()
    return member


async def _get_scoped(member_id: uuid.UUID, user: User, db: AsyncSession) -> FamilyMember:
    hid = await _household_id(user, db)
    member = await db.get(FamilyMember, member_id)
    if member is None or member.household_id != hid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


@router.get("/{member_id}", response_model=MemberResponse)
async def get_member(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    return await _get_scoped(member_id, user, db)


@router.patch("/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    member = await _get_scoped(member_id, user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    await db.flush()
    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    member = await _get_scoped(member_id, user, db)
    await db.delete(member)
    await db.flush()


MEDICATIONS_MERGE_SYSTEM = (
    "You maintain a patient's current-medications list. Merge the existing "
    "list with newly filed medications into ONE plain-text list: one "
    "medicine per line as 'name — dose, timing'. Keep drug names verbatim, "
    "drop lines that duplicate another, never invent medicines, and add "
    "nothing else — no preamble, no numbering, no commentary."
)


@router.post(
    "/{member_id}/current-medications/merge",
    response_model=MedicationMergeSuggestion,
)
async def merge_current_medications(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationMergeSuggestion:
    """Suggest an updated current-medications list: the member's existing
    free-text list merged with their active tracked medications. Nothing is
    persisted — the client accepts (PATCH) or dismisses."""
    member = await get_scoped_member(member_id, user, db)
    active = list(
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member.id,
                Medication.status == "active",
            )
        )
    )
    plan = await ai_router.plan_for_household(db, member.household_id)
    provider = await ai_router.first_available(plan)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider available")
    tracked = (
        "\n".join(
            f"{m.medicine} — {m.dosage or 'dose not recorded'}, {m.timing or 'timing not recorded'}"
            for m in active
        )
        or "(none tracked)"
    )
    prompt = (
        f"Existing current-medications list:\n"
        f"{member.current_medications or '(empty)'}\n\n"
        f"Newly tracked active medications:\n{tracked}\n\n"
        "Return the merged list only."
    )
    raw = await provider.complete(prompt, system=MEDICATIONS_MERGE_SYSTEM, max_tokens=600)
    # Plain-text list, not JSON — only strip thinking-model wrappers.
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    return MedicationMergeSuggestion(suggestion=cleaned)
