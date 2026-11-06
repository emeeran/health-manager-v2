"""Push subscription management."""

from sqlalchemy import select

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import PushSubscription, User
from app.services import web_push_service

router = APIRouter(prefix="/notifications/push", tags=["push"])


class SubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=500)
    keys: dict[str, str]


class UnsubscribeRequest(BaseModel):
    endpoint: str


@router.get("/status")
async def push_status(_: User = Depends(get_current_user)) -> dict:
    return web_push_service.vapid_status()


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(
    body: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not web_push_service.push_configured():
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Web push not configured")
    p256dh = body.keys.get("p256dh", "")
    auth = body.keys.get("auth", "")
    if not p256dh or not auth:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "keys incomplete")
    existing = (
        await db.scalars(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    ).first()
    if existing:  # idempotent re-subscribe
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, p256dh=p256dh, auth=auth))
    await db.commit()
    return {"subscribed": True}


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    body: UnsubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == body.endpoint,
        )
    )
    await db.commit()
