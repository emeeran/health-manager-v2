"""In-app notifications: list, unread count, mark read."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_membership
from app.models import User
from app.services import notifications as notifications_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = await get_household_membership(user, db)
    items = await notifications_service.list_notifications(
        db, household.id, user.id, limit=min(limit, 200)
    )
    return {
        "items": items,
        "unread": await notifications_service.unread_count(db, household.id, user.id),
    }


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = await get_household_membership(user, db)
    return {"unread": await notifications_service.unread_count(db, household.id, user.id)}


@router.post("/read-all")
async def read_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = await get_household_membership(user, db)
    marked = await notifications_service.mark_all_read(db, household.id, user.id)
    await db.commit()
    return {"marked": marked}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = await get_household_membership(user, db)
    if not await notifications_service.mark_read(db, notification_id, household.id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    await db.commit()
    return {"ok": True}
