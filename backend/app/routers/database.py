"""Database integrity card router (Data tab)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.services.database_maintenance import check_integrity

router = APIRouter(prefix="/database", tags=["database"])


@router.get("/integrity")
async def get_integrity(
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read-only structural integrity scan. Safe for any authenticated user."""
    return await check_integrity(db)
