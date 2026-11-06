"""Household dashboard: scores, alerts, activity, family strip."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id
from app.models import User
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregated household overview.

    Deterministic aggregation only (no AI): health scores with
    breakdowns, alerts (overdue boosters, abnormal labs, low adherence,
    allergy-med conflicts), a cross-member activity feed, vaccination
    status, medication summary, and the per-member strip. Shape mirrors
    v1's /dashboard/summary minus the preventive-care section (no v2
    PreventiveCareService yet).
    """
    hid = await get_household_id(user, db)
    return await DashboardService(db).get_household_summary(hid)
