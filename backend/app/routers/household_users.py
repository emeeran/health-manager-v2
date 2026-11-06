"""Household user administration: members, roles, invitations.

Invitation accept doubles as registration-by-invitation — it works even
when open registration is disabled (the token is the authorization), and is
the production path for adding users.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_household_admin
from app.core.security import hash_password
from app.models import (
    HouseholdInvitation,
    HouseholdMember,
    HouseholdRole,
    RefreshToken,
    User,
)
from app.schemas.auth import AuthResponse
from app.schemas.household import (
    HouseholdUserInfo,
    InvitationAccept,
    InvitationCreated,
    InvitationInfo,
    RoleUpdate,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/household/users", tags=["household-users"])

INVITE_TTL_DAYS = 7


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _scoping(user: User, db: AsyncSession):
    """(household_id, my_role, primary_user_id) for the caller."""
    from app.core.deps import get_household_membership

    household, role = await get_household_membership(user, db)
    return household.id, role, household.primary_user_id


@router.get("", response_model=list[HouseholdUserInfo])
async def list_users(
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> list[HouseholdUserInfo]:
    household, _ = result
    rows = (
        await db.execute(
            select(HouseholdMember, User)
            .join(User, User.id == HouseholdMember.user_id)
            .where(HouseholdMember.household_id == household.id)
            .order_by(HouseholdMember.created_at)
        )
    ).all()
    return [
        HouseholdUserInfo(
            user_id=member.user_id,
            username=user.username,
            role=member.role,
            is_primary=member.user_id == household.primary_user_id,
            created_at=member.created_at,
        )
        for member, user in rows
    ]


async def _member(household_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession):
    member = await db.scalar(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == user_id,
        )
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not in household")
    return member


@router.patch("/{user_id}", response_model=HouseholdUserInfo)
async def set_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> HouseholdUserInfo:
    household, _ = result
    household_id = household.id
    member = await _member(household_id, user_id, db)
    target = await db.get(User, user_id)
    if target is None:  # pragma: no cover — FK guarantees existence
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user_id == household.primary_user_id and body.role != (HouseholdRole.ADMIN.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The household owner always stays admin")
    if member.role == HouseholdRole.ADMIN.value and body.role != (HouseholdRole.ADMIN.value):
        admins = await db.scalar(
            select(func.count())
            .select_from(HouseholdMember)
            .where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.role == HouseholdRole.ADMIN.value,
            )
        )
        if (admins or 0) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot demote the last admin")
    member.role = body.role
    record_audit(
        db,
        action="household.role_change",
        household_id=household_id,
        user_id=user_id,
        detail=f"{target.username} -> {body.role}",
        ip=request.client.host if request.client else None,
    )
    await db.flush()
    return HouseholdUserInfo(
        user_id=user_id,
        username=target.username,
        role=member.role,
        is_primary=user_id == household.primary_user_id,
        created_at=member.created_at,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(
    user_id: uuid.UUID,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    household, _ = result
    household_id = household.id
    if user_id == household.primary_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The household owner cannot be removed")
    member = await _member(household_id, user_id, db)
    target = await db.get(User, user_id)
    # Users belong to exactly one household — removal deactivates the account
    # rather than leaving it household-less (login would 500).
    if target is not None:
        target.is_active = False
    await db.delete(member)
    record_audit(
        db,
        action="household.user_removed",
        household_id=household_id,
        user_id=user_id,
        detail=target.username if target else str(user_id),
        ip=request.client.host if request.client else None,
    )
    await db.flush()


@router.post("/invitations", response_model=InvitationCreated, status_code=201)
async def create_invitation(
    body: RoleUpdate,
    request: Request,
    result: tuple = Depends(require_household_admin),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvitationCreated:
    household_id = result[0].id
    raw = secrets.token_urlsafe(32)
    invitation = HouseholdInvitation(
        household_id=household_id,
        token_hash=_hash_token(raw),
        role=body.role,
        invited_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invitation)
    await db.flush()
    record_audit(
        db,
        action="household.invite_created",
        household_id=household_id,
        detail=f"role={body.role}",
        ip=request.client.host if request.client else None,
    )
    return InvitationCreated(
        id=invitation.id,
        token=raw,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@router.get("/invitations", response_model=list[InvitationInfo])
async def list_invitations(
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> list[InvitationInfo]:
    household_id = result[0].id
    rows = (
        await db.scalars(
            select(HouseholdInvitation)
            .where(HouseholdInvitation.household_id == household_id)
            .order_by(HouseholdInvitation.created_at.desc())
        )
    ).all()
    return [
        InvitationInfo(
            id=row.id,
            role=row.role,
            expires_at=row.expires_at,
            accepted=row.accepted_at is not None,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    household_id = result[0].id
    row = await db.get(HouseholdInvitation, invitation_id)
    if row is None or row.household_id != household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    await db.delete(row)
    record_audit(
        db,
        action="household.invite_revoked",
        household_id=household_id,
        ip=request.client.host if request.client else None,
    )
    await db.flush()


@router.post("/invitations/accept", response_model=AuthResponse)
async def accept_invitation(
    body: InvitationAccept,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register a new account into the inviting household (sets auth cookies)."""
    row = await db.scalar(
        select(HouseholdInvitation).where(HouseholdInvitation.token_hash == _hash_token(body.token))
    )
    now = datetime.now(UTC)
    if row is None or row.accepted_at is not None or row.expires_at.replace(tzinfo=UTC) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invitation is invalid, used, or expired")
    existing = await db.scalar(select(User).where(User.username == body.username))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    db.add(
        HouseholdMember(
            household_id=row.household_id,
            user_id=user.id,
            role=row.role,
            invited_by=row.invited_by,
        )
    )
    row.accepted_at = now
    record_audit(
        db,
        action="household.invite_accepted",
        household_id=row.household_id,
        user_id=user.id,
        detail=f"{user.username} as {row.role}",
    )

    # Issue auth cookies (same discipline as /auth/login).
    from app.core.security import create_access_token
    from app.routers.auth import _new_refresh_value, _set_cookies

    access, _ = create_access_token(str(user.id))
    refresh_value = _new_refresh_value()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashlib.sha256(refresh_value.encode()).hexdigest(),
            expires_at=now + timedelta(days=get_settings().REFRESH_TOKEN_DAYS),
        )
    )
    _set_cookies(response, access, refresh_value)
    await db.commit()
    return AuthResponse.model_validate(user)
