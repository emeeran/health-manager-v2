"""Drug-catalog endpoints (Jan Aushadhi generic catalog, seeded from bundled CSV).

Powers ingredient matching for later allergy-conflict lookups and generic
price comparison. Catalog rows are metadata — never a purchase channel.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import Insight, User
from app.services import crawler_drug_service, local_drug_service
from app.services.ai import router as ai_router

router = APIRouter(prefix="/drugs", tags=["drugs"])


@router.get("/search")
async def search_drugs(
    q: str = Query(..., min_length=2, description="Name fragment (brand or generic)"),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Jan Aushadhi generic rows first, then crawled pharmacy listings.

    Crawler rows carry ``catalog`` ("1mg"/"apollo") and ``url`` instead of
    ``product_id``; they are already sorted by selling price ascending."""
    rows = await local_drug_service.search_local_drugs(db, q, limit)
    crawler_rows = await crawler_drug_service.search_crawler_drugs(db, q, limit)
    return [
        {
            "id": str(row.id),
            "catalog": "jan_aushadhi",
            "product_id": row.product_id,
            "name": row.name,
            "manufacturer": row.manufacturer,
            "ingredients": local_drug_service.parsed_ingredients(row),
            "price": row.price,
            "product_form": row.product_form,
            "package": row.package,
        }
        for row in rows
    ] + [
        {
            "id": str(row.id),
            "catalog": row.source,
            "product_id": None,
            "name": row.brand_name,
            "manufacturer": row.manufacturer,
            "ingredients": [],
            "price": row.price_selling,
            "price_mrp": row.price_mrp,
            "product_form": row.dosage_form,
            "package": row.pack_size,
            "url": row.url,
            "prescription_required": row.prescription_required,
        }
        for row in crawler_rows
    ]


class PriceCompareRequest(BaseModel):
    medicines: list[str] = Field(min_length=1, max_length=15)
    narrate: bool = True
    # Optional: scopes the narrative to a member (consent gating, insight
    # persistence). Omitted → local-only providers, nothing persisted.
    member_id: uuid.UUID | None = None


@router.post("/price-compare")
async def price_compare(
    body: PriceCompareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Deterministic price table over the catalog, plus an OPTIONAL grounded
    narrative: the model sees only the computed table and may state nothing
    that is not in it. The table itself is never a model claim."""
    names = [m.strip() for m in body.medicines if m and m.strip()]
    if not names:
        raise HTTPException(422, "At least one medicine name is required")

    member = None
    if body.member_id is not None:
        member = await get_scoped_member(body.member_id, user, db)

    result = await local_drug_service.compare_prices(db, names)
    # Pharmacy offers from the crawled 1mg/Apollo catalog — cheapest first,
    # match discipline identical to the Jan Aushadhi tiers.
    offers_matched = 0
    for item in result["items"]:
        offers = await crawler_drug_service.offers_for(db, item["medicine"])
        item["pharmacy_offers"] = offers
        if offers:
            offers_matched += 1
    result["offers_matched_count"] = offers_matched
    narrative = None
    provider_used = None
    if body.narrate:
        plan = ai_router.build_plan(
            local_only=member is not None and not member.cloud_ai_consent
        )
        provider = await ai_router.first_available(plan)
        if provider is not None:
            prompt = local_drug_service.PRICE_NARRATIVE_PROMPT.format(
                table=json.dumps(result, ensure_ascii=False, indent=1)
            )
            try:
                narrative = (await provider.complete(prompt)).strip()
            except Exception:  # noqa: BLE001 — narrative failure keeps the table
                narrative = None
            provider_used = provider.name
            if member is not None and narrative:
                db.add(
                    Insight(
                        member_id=member.id,
                        kind="price_comparison",
                        content=narrative,
                        sources_json=json.dumps(result, ensure_ascii=False),
                        provider_used=provider.name,
                    )
                )
                await db.flush()

    return {**result, "narrative": narrative, "provider_used": provider_used}
