"""Web Push (VAPID-gated).

Inert unless WEB_PUSH_ENABLED + VAPID keys are configured. Dispatch
prunes subscriptions the push endpoint reports as gone (404/410).
"""

import json
from datetime import UTC, datetime

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import PushSubscription


def push_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.WEB_PUSH_ENABLED
        and settings.WEB_PUSH_VAPID_PRIVATE_KEY
        and settings.WEB_PUSH_VAPID_PUBLIC_KEY
    )


def vapid_status() -> dict:
    settings = get_settings()
    enabled = push_configured()
    return {
        "enabled": enabled,
        "public_key": settings.WEB_PUSH_VAPID_PUBLIC_KEY if enabled else None,
    }


def _vapid_claims() -> dict:
    return {"sub": get_settings().WEB_PUSH_VAPID_SUBJECT}


def send_to_subscription(
    subscription: PushSubscription, title: str, message: str
) -> tuple[bool, bool]:
    """Send one push. Returns (sent, gone): `gone` True means the endpoint
    reported the subscription dead (404/410) and the caller should prune."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "message": message}),
            vapid_private_key=get_settings().WEB_PUSH_VAPID_PRIVATE_KEY,
            vapid_claims=_vapid_claims(),
        )
        return True, False
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        return False, status_code in (404, 410)
    except OSError:
        return False, False  # network error — transient, keep subscription


async def dispatch_pending(db: AsyncSession) -> dict:
    """Push undelivered notifications to every subscription (watermark-based).

    v1 watermark semantics: each subscription carries a ``last_pushed_at``
    watermark; unread notifications created *after* the watermark are pushed
    (newest-capped at 10) and the watermark is stamped even when nothing was
    pending, so dispatched items are pruned from future dispatches by
    construction — a double run re-sends nothing. Dead endpoints (404/410)
    drop the subscription. Idempotent: disabled config short-circuits.
    """
    if not push_configured():
        return {"delivered": 0, "failed": 0, "disabled": True}

    from app.core.encryption import decrypt_secret
    from app.models import Notification

    subs = (await db.scalars(select(PushSubscription))).all()
    delivered = 0
    failed = 0
    now = datetime.now(UTC)
    for sub in subs:
        since = sub.last_pushed_at
        query = (
            select(Notification)
            .where(
                (Notification.user_id.is_(None)) | (Notification.user_id == sub.user_id),
                Notification.read_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
            .limit(10)
        )
        if since is not None:
            # Naive vs aware: columns may be either; compare on naive UTC.
            query = query.where(
                Notification.created_at > since.replace(tzinfo=None)
                if since.tzinfo
                else Notification.created_at > since
            )
        pending = (await db.scalars(query)).all()
        # Stamp even with nothing pending, so the watermark advances.
        sub.last_pushed_at = now
        for n in pending:
            was_sent, gone = send_to_subscription(
                sub,
                decrypt_secret(n.title_encrypted) or "",
                decrypt_secret(n.body_encrypted) or "",
            )
            if was_sent:
                delivered += 1
            else:
                failed += 1
                if gone:
                    await db.delete(sub)
                    break
    await db.commit()
    return {"delivered": delivered, "failed": failed}


async def push_to_user(db: AsyncSession, user_id, title: str, message: str) -> int:
    """Push to all of a user's subscriptions; prunes only dead endpoints."""
    subs = (
        await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).all()
    sent = 0
    dead: list[PushSubscription] = []
    for sub in subs:
        was_sent, gone = send_to_subscription(sub, title, message)
        if was_sent:
            sub.last_pushed_at = datetime.now(UTC)
            sent += 1
        if gone:
            dead.append(sub)
    for sub in dead:
        await db.delete(sub)
    if dead:
        await db.commit()
    return sent
