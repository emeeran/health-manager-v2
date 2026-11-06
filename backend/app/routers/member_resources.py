"""Health-resources lookup — patient education / official label metadata.

Metadata only (title / url / summary): page bodies are never proxied; the
client opens the source link directly.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.services import health_resources_service

router = APIRouter(prefix="/members/{member_id}/resources", tags=["health-resources"])


@router.get("")
async def get_health_resource(
    member_id: uuid.UUID,
    term: str = Query(..., description="Drug name or term to look up"),
    source: str = Query(..., description="medlineplus | dailymed | hc-dpd | mhra"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not term.strip():
        raise HTTPException(422, "term query parameter is required")
    if source not in health_resources_service.SOURCES:
        raise HTTPException(422, "source must be one of: medlineplus, dailymed, hc-dpd, mhra")
    await get_scoped_member(member_id, user, db)
    results = await health_resources_service.lookup(term.strip(), source)
    if not results:
        raise HTTPException(404, "No resources found for term")
    top = results[0]
    return {
        "title": top.get("title"),
        "url": top.get("url"),
        "summary": top.get("summary"),
        "source": source,
    }
