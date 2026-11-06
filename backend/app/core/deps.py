"""Route dependencies: token resolution and current-user lookup.

Token preference: httpOnly `access_token` cookie first, Authorization
Bearer header fallback — so both browser and scripted clients work.
"""

import uuid

from typing import TYPE_CHECKING

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

if TYPE_CHECKING:
    from app.models import Household

COOKIE_NAME = "access_token"


def _resolve_token(request: Request) -> str | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    from fastapi import HTTPException, status

    token = _resolve_token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    claims = decode_access_token(token)
    if not claims or claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    try:
        sub = uuid.UUID(claims["sub"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from None
    user = await db.get(User, sub)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


async def get_optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    try:
        return await get_current_user(request, db)
    except Exception:
        return None


async def get_scoped_member(member_id: uuid.UUID, user: User, db: AsyncSession):
    """Fetch a family member, 404 unless it belongs to the caller's household."""
    from fastapi import HTTPException, status

    from app.models import FamilyMember

    household_id = await get_household_id(user, db)
    member = await db.get(FamilyMember, member_id)
    if member is None or member.household_id != household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


def require_registration_open():
    from fastapi import HTTPException, status

    from app.core.config import get_settings

    if not get_settings().registration_open:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled on this instance")


async def get_household_membership(user: User, db: AsyncSession) -> tuple["Household", str]:
    """Resolve (household, role) for the caller.

    Role comes from household_members; the legacy primary_user_id path
    resolves to admin so pre-phase-8 single-user households keep access.
    """
    from fastapi import HTTPException, status

    from sqlalchemy import select

    from app.models import Household, HouseholdMember, HouseholdRole

    row = (
        await db.execute(
            select(Household, HouseholdMember)
            .join(HouseholdMember, HouseholdMember.household_id == Household.id)
            .where(HouseholdMember.user_id == user.id)
        )
    ).first()
    if row is not None:
        return row[0], row[1].role
    household = await db.scalar(select(Household).where(Household.primary_user_id == user.id))
    if household is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No household")
    return household, HouseholdRole.ADMIN.value


async def get_household_id(user: User, db: AsyncSession) -> uuid.UUID:
    """Household id for the caller, via the membership-aware resolution."""
    household, _ = await get_household_membership(user, db)
    return household.id


async def require_household_admin(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Dependency: 403 unless the caller is a household admin.

    Returns (household, role) so handlers can reuse the resolution.
    """
    from fastapi import HTTPException, status

    from app.models import HouseholdRole

    household, role = await get_household_membership(user, db)
    if role != HouseholdRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Household admin role required")
    return household, role
