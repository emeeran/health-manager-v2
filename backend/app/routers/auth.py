"""Auth routes: register, login, refresh, logout, me.

Cookies: access_token (httpOnly, path=/, 30 min) and refresh_token
(httpOnly, path=/api/v1/auth, 7 days, DB-backed by hash). Bearer fallback
is accepted by deps for scripted clients.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_registration_open
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import Household, RefreshToken, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TwoFactorCodeRequest,
    TwoFactorLoginRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _hash_refresh(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _new_refresh_value() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def _set_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=access,
        httponly=True,
        samesite="strict",
        secure=settings.is_production,
        max_age=settings.ACCESS_TOKEN_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh,
        httponly=True,
        samesite="strict",
        secure=settings.is_production,
        max_age=settings.REFRESH_TOKEN_DAYS * 86400,
        path="/api/v1/auth",
    )


async def _issue(response: Response, user: User, db: AsyncSession) -> AuthResponse:
    access, _ = create_access_token(str(user.id))
    refresh_value = _new_refresh_value()
    settings = get_settings()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_refresh(refresh_value),
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )
    )
    await db.commit()
    _set_cookies(response, access, refresh_value)
    return AuthResponse.model_validate(user)


@router.post("/register", response_model=AuthResponse)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_registration_open),
) -> AuthResponse:
    existing = await db.scalar(select(User).where(User.username == body.username))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    from app.models import HouseholdMember, HouseholdRole

    household = Household(name=body.household_name, primary_user_id=user.id)
    db.add(household)
    await db.flush()
    db.add(
        HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role=HouseholdRole.ADMIN.value,
        )
    )
    return await _issue(response, user, db)


@router.post("/login")
async def login(
    body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> Any:  # AuthResponse, or {"requires_2fa": true}
    user = await db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    from app.services.audit import record_audit

    record_audit(db, action="auth.login", user_id=user.id)
    if user.totp_enabled and not body.code:
        return {"requires_2fa": True}
    if user.totp_enabled and body.code:
        # Code provided on the main login — accept TOTP or backup code.
        from app.services import totp_service

        if not (
            totp_service.verify_totp(user, body.code)
            or totp_service.verify_backup_code(db, user, body.code)
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid 2FA code")
        await db.commit()
    return await _issue(response, user, db)


@router.post("/login/2fa")
async def login_2fa(
    body: TwoFactorLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Complete a 2FA login: password + TOTP (or backup) code."""
    from app.services import totp_service

    user = await db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA is not enabled")
    if not (
        totp_service.verify_totp(user, body.code)
        or totp_service.verify_backup_code(db, user, body.code)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid 2FA code")
    await db.commit()
    return await _issue(response, user, db)


@router.post("/2fa/setup")
async def setup_2fa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services import totp_service

    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA already enabled")
    result = totp_service.setup(db, user)
    await db.commit()
    return result


@router.post("/2fa/verify")
async def verify_2fa(
    body: TwoFactorCodeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services import totp_service

    if not totp_service.confirm_enable(db, user, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    await db.commit()
    return {"enabled": True}


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_2fa(
    body: TwoFactorCodeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    from fastapi import HTTPException as _HTTPException

    from app.services import totp_service

    if not totp_service.disable(db, user, body.code):
        raise _HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    await db.commit()


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    value = request.cookies.get(REFRESH_COOKIE)
    if not value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(value))
    )
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at.replace(tzinfo=UTC) < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    row.revoked_at = now  # rotation: single use
    return await _issue(response, user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    value = request.cookies.get(REFRESH_COOKIE)
    if value:
        row = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(value))
        )
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    await db.commit()


@router.get("/me", response_model=AuthResponse)
async def me(user: User = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse.model_validate(user)
