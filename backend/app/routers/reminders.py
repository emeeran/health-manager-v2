"""Household reminder CRUD."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import Reminder, User
from app.schemas.reminder import ReminderCreate, ReminderResponse, ReminderUpdate

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderResponse])
async def list_reminders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Reminder]:
    rows = await db.scalars(select(Reminder).order_by(Reminder.remind_at).limit(500))
    return list(rows)


@router.post("", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Reminder:
    if body.member_id:
        await get_scoped_member(body.member_id, user, db)
    reminder = Reminder(**body.model_dump())
    db.add(reminder)
    await db.flush()
    await db.refresh(reminder)
    return reminder


async def _get_reminder(reminder_id: uuid.UUID, db: AsyncSession) -> Reminder:
    reminder = await db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    return reminder


@router.patch("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(
    reminder_id: uuid.UUID,
    body: ReminderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Reminder:
    reminder = await _get_reminder(reminder_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(reminder, field, value)
    await db.flush()
    await db.refresh(reminder)
    return reminder


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    reminder = await _get_reminder(reminder_id, db)
    await db.delete(reminder)
    await db.flush()
