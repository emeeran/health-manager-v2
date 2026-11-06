"""Drug-interaction analysis across a member's active medications (AI-powered).

The medication snapshot is deterministic (computed in code); the AI provider
supplies the pairwise analysis in structured form. Results persist as an
Insight (kind="drug_interactions", kind-scoped latest wins).
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import Insight, Medication, User
from app.services import drug_interaction_service
from app.services.ai import router as ai_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members/{member_id}/drug-interactions", tags=["drug-interactions"])


@router.post("")
async def analyze_drug_interactions(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    member = await get_scoped_member(member_id, user, db)
    meds = list(await db.scalars(select(Medication).where(Medication.member_id == member_id)))
    snapshot = drug_interaction_service.build_snapshot(meds)
    if len(snapshot.medicines) < 2:
        return {
            "interactions": [],
            "provider_used": None,
            "medications_checked": len(snapshot.medicines),
        }

    plan = ai_router.build_plan(local_only=not member.cloud_ai_consent)
    provider = await ai_router.first_available(plan)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider available")

    prompt = drug_interaction_service.INTERACTION_PROMPT.format(med_list=snapshot.prompt_list)
    try:
        reply = await provider.complete(prompt)
    except Exception:  # noqa: BLE001 — a failed check degrades to empty
        logger.warning("Drug-interaction AI call failed", exc_info=True)
        reply = ""

    interactions = drug_interaction_service.parse_interactions(reply or "")
    db.add(
        Insight(
            member_id=member_id,
            kind="drug_interactions",
            content=json.dumps(interactions),
            sources_json=json.dumps(snapshot.medicines),
            provider_used=provider.name,
        )
    )
    await db.flush()

    return {
        "interactions": interactions,
        "provider_used": provider.name,
        "medications_checked": len(snapshot.medicines),
    }
