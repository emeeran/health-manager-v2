"""Cross-member household search (FTS5 over the search mirror)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id
from app.models import User
from app.services import search_index_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def household_search(
    q: str = Query(..., min_length=2, max_length=200),
    member_id: uuid.UUID | None = None,
    limit: int = Query(default=20, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """BM25-ranked search across the caller's household.

    Results are [{row_type, row_id, member_id, member_name, title,
    snippet, score}] — higher score is better. Never logs the mirror body
    (plaintext PHI by design, same trust domain as the DB itself).
    """
    hid = await get_household_id(user, db)
    return await search_index_service.search(db, hid, q, member_id, limit)


@router.post("/reindex")
async def reindex_search(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rebuild the household's search mirror from the domain tables.

    Full rebuild is deliberate at this scale (few thousand rows per
    household) — it is always correct without per-write hooks.
    """
    hid = await get_household_id(user, db)
    indexed = await search_index_service.reindex_all(db, hid)
    return {"indexed": indexed}
