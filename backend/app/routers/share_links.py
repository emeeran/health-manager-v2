"""Expiring read-only member share links (token = credential)."""

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import (
    Allergy,
    ConditionEpisode,
    FamilyMember,
    Medication,
    ShareLink,
    User,
)

router = APIRouter(prefix="/members/{member_id}/share-links", tags=["share"])
public_router = APIRouter(prefix="/public/share", tags=["share"])


class ShareLinkCreate(BaseModel):
    expires_days: int = Field(default=7, ge=1, le=90)


class ShareLinkView(BaseModel):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime | None
    revoked: bool


class ShareLinkCreated(BaseModel):
    id: uuid.UUID
    token_shown_once: str
    expires_at: datetime | None


@router.post("", response_model=ShareLinkCreated, status_code=status.HTTP_201_CREATED)
async def create_share_link(
    member_id: uuid.UUID,
    body: ShareLinkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareLinkCreated:
    await get_scoped_member(member_id, user, db)
    token = uuid.uuid4().hex + uuid.uuid4().hex
    link = ShareLink(
        member_id=member_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=body.expires_days),
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)
    return ShareLinkCreated(id=link.id, token_shown_once=token, expires_at=link.expires_at)


@router.get("", response_model=list[ShareLinkView])
async def list_share_links(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ShareLinkView]:
    await get_scoped_member(member_id, user, db)
    rows = await db.scalars(
        select(ShareLink)
        .where(ShareLink.member_id == member_id)
        .order_by(ShareLink.created_at.desc())
    )
    return [
        ShareLinkView(
            id=row.id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked=row.revoked_at is not None,
        )
        for row in rows
    ]


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_link(
    member_id: uuid.UUID,
    link_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_scoped_member(member_id, user, db)
    link = await db.get(ShareLink, link_id)
    if link is None or link.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.revoked_at is None:
        from datetime import datetime as dt

        link.revoked_at = dt.now(UTC)
    await db.flush()


# ── Public, unauthenticated (the token IS the credential) ─────────────


class PublicShareResponse(BaseModel):
    member: dict
    medications: list[dict]
    allergies: list[dict]
    conditions: list[dict]
    generated_at: datetime


def _age_years(birth_date) -> int | None:  # noqa: ANN001
    if birth_date is None:
        return None
    birth = date(birth_date.year, birth_date.month, birth_date.day)
    today = datetime.now(UTC).date()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


@public_router.get("/{token}", response_model=PublicShareResponse)
async def public_share(
    token: str,
    _: None = None,  # no auth — token is the credential
    db: AsyncSession = Depends(get_db),
) -> PublicShareResponse:
    link = await db.scalar(
        select(ShareLink).where(ShareLink.token_hash == hashlib.sha256(token.encode()).hexdigest())
    )
    now = datetime.now(UTC)
    if link is None or link.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.expires_at is not None and link.expires_at.replace(tzinfo=UTC) < now:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link expired")

    member = await db.get(FamilyMember, link.member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")

    meds = (
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member.id, Medication.status == "active"
            )
        )
    ).all()
    allergies = (await db.scalars(select(Allergy).where(Allergy.member_id == member.id))).all()
    conditions = (
        await db.scalars(
            select(ConditionEpisode).where(
                ConditionEpisode.member_id == member.id,
                ConditionEpisode.status != "resolved",
            )
        )
    ).all()

    return PublicShareResponse(
        member={
            "name": member.name,
            "relationship": member.relationship,
            "age_years": _age_years(member.birth_date),
        },
        medications=[{"medicine": m.medicine, "dosage": m.dosage} for m in meds],
        allergies=[{"substance": a.substance, "severity": a.severity} for a in allergies],
        conditions=[{"name": c.name, "status": c.status} for c in conditions],
        generated_at=now,
    )
