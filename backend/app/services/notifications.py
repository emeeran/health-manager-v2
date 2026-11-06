"""In-app notification creation + query helpers.

Creation is household-scoped with an optional per-user target (NULL =
everyone in the household); list endpoints decrypt title/body at read time.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import Notification


def create_notification(
    db: AsyncSession,
    *,
    household_id: uuid.UUID,
    title: str,
    body: str | None = None,
    user_id: uuid.UUID | None = None,
) -> Notification:
    row = Notification(
        household_id=household_id,
        user_id=user_id,
        title_encrypted=encrypt_secret(title) or "",
        body_encrypted=encrypt_secret(body),
    )
    db.add(row)
    return row


def _visible(user_id: uuid.UUID):
    return (Notification.user_id.is_(None)) | (Notification.user_id == user_id)


async def list_notifications(
    db: AsyncSession, household_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50
) -> list[dict]:
    rows = (
        await db.scalars(
            select(Notification)
            .where(Notification.household_id == household_id, _visible(user_id))
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "title": decrypt_secret(row.title_encrypted) or "",
            "body": decrypt_secret(row.body_encrypted) or "",
            "read": row.read_at is not None,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


async def unread_count(db: AsyncSession, household_id: uuid.UUID, user_id: uuid.UUID) -> int:
    rows = await db.scalars(
        select(Notification.read_at).where(
            Notification.household_id == household_id,
            Notification.read_at.is_(None),
            _visible(user_id),
        )
    )
    return sum(1 for _ in rows)


async def mark_read(
    db: AsyncSession,
    notification_id: uuid.UUID,
    household_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    row = await db.get(Notification, notification_id)
    if (
        row is None
        or row.household_id != household_id
        or (row.user_id is not None and row.user_id != user_id)
    ):
        return False
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
    return True


async def mark_all_read(db: AsyncSession, household_id: uuid.UUID, user_id: uuid.UUID) -> int:
    rows = (
        await db.scalars(
            select(Notification).where(
                Notification.household_id == household_id,
                Notification.read_at.is_(None),
                _visible(user_id),
            )
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    return len(rows)
