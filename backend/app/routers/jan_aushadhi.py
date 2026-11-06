"""Drug-catalog search (Jan Aushadhi generic catalog, seeded from bundled CSV).

Powers ingredient matching for later allergy-conflict lookups and generic
price comparison. Catalog rows are metadata — never a purchase channel.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.services import local_drug_service

router = APIRouter(prefix="/drugs", tags=["drugs"])


@router.get("/search")
async def search_drugs(
    q: str = Query(..., min_length=2, description="Name fragment (brand or generic)"),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await local_drug_service.search_local_drugs(db, q, limit)
    return [
        {
            "id": str(row.id),
            "product_id": row.product_id,
            "name": row.name,
            "manufacturer": row.manufacturer,
            "ingredients": local_drug_service.parsed_ingredients(row),
            "price": row.price,
            "product_form": row.product_form,
            "package": row.package,
        }
        for row in rows
    ]
