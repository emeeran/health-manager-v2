"""Health alerts: member-scoped listing + acknowledge.

Alerts are created by the extraction pipeline (flagged lab values); this
router is the read/acknowledge side.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.services import health_alert_service

router = APIRouter(prefix="/members/{member_id}/health-alerts", tags=["health-alerts"])


@router.get("")
async def list_health_alerts(
    member_id: uuid.UUID,
    unacknowledged_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await get_scoped_member(member_id, user, db)
    alerts = await health_alert_service.list_alerts(
        db, member_id, unacknowledged_only=unacknowledged_only
    )
    return [health_alert_service.alert_view(a) for a in alerts]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_health_alert(
    member_id: uuid.UUID,
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await get_scoped_member(member_id, user, db)
    try:
        alert = await health_alert_service.acknowledge_alert(db, member_id, alert_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found") from None
    return health_alert_service.alert_view(alert)
