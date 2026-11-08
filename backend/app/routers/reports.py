"""Report generation endpoints (SSE) + latest read-back.

One endpoint shape for the whole report family:
``POST /members/{id}/reports/{kind}/stream`` and
``GET /members/{id}/reports/{kind}/latest``. The legacy
``/reports/smart/stream`` and ``/reports/pre-consultation/stream`` routes
are kept as aliases. Kinds: smart_report, health_insights, pre_consultation,
consultant_note, consolidated_report, medication_report,
medication_schedule, forecast — each a deterministic snapshot plus one
AI narrative (the model narrates, never invents numbers).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.core.sse import sse_response
from app.models import User
from app.services import report_service

router = APIRouter(prefix="/members/{member_id}/reports", tags=["reports"])

VALID_KINDS = (
    "smart_report",
    "health_insights",
    "pre_consultation",
    "consultant_note",
    "consolidated_report",
    "medication_report",
    "medication_schedule",
    "forecast",
    "visit_summary",
)

# URL slugs → kind (underscore kind also accepted).
KIND_SLUGS = {
    "smart_report": "smart_report",
    "smart": "smart_report",
    "health_insights": "health_insights",
    "health-insights": "health_insights",
    "health-insight": "health_insights",
    "pre_consultation": "pre_consultation",
    "pre-consultation": "pre_consultation",
    "consultant_note": "consultant_note",
    "consultant-note": "consultant_note",
    "consolidated_report": "consolidated_report",
    "consolidated-report": "consolidated_report",
    "consolidated": "consolidated_report",
    "medication_report": "medication_report",
    "medication-report": "medication_report",
    "medication_schedule": "medication_schedule",
    "medication-schedule": "medication_schedule",
    "forecast": "forecast",
    "visit_summary": "visit_summary",
    "visit-summary": "visit_summary",
}


class ReportView(BaseModel):
    id: uuid.UUID
    kind: str
    content: str
    sources: dict | None
    verification_id: uuid.UUID | None
    provider_used: str | None
    created_at: object

    model_config = {"from_attributes": True}


def _resolve_kind(slug: str) -> str:
    kind = KIND_SLUGS.get(slug)
    if kind is None or kind not in VALID_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown report kind")
    return kind


def _to_view(insight) -> dict:
    import json

    return {
        "id": str(insight.id),
        "kind": insight.kind,
        "content": insight.content,
        "sources": json.loads(insight.sources_json) if insight.sources_json else None,
        "verification_id": str(insight.verification_id) if insight.verification_id else None,
        "provider_used": insight.provider_used,
        "created_at": insight.created_at.isoformat(),
    }


async def _stream_kind(
    member_id: uuid.UUID,
    slug: str,
    user: User,
    db: AsyncSession,
    record_id: uuid.UUID | None = None,
    note: str | None = None,
):
    from app.routers.ai_insights import resolve_ai_provider
    from app.models import HealthRecord

    kind = _resolve_kind(slug)
    if kind == "visit_summary":
        # Per-visit kind: the record must exist, belong to this member, and
        # not be deleted — a cross-member or missing record is 404, absent
        # record_id is 422 before any AI call is made.
        if record_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "record_id required for visit_summary",
            )
        record = await db.get(HealthRecord, record_id)
        if (
            record is None
            or record.member_id != member_id
            or record.is_deleted
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit record not found")
    provider, verifier = await resolve_ai_provider(member_id, user, db)
    source = report_service.report_stream(
        db,
        member_id,
        kind,
        provider,
        verifier,
        record_id=record_id,
        user_note=note,
    )
    return sse_response(source)


@router.post("/{kind}/stream")
async def report_stream_endpoint(
    member_id: uuid.UUID,
    kind: str,
    record_id: uuid.UUID | None = None,
    note: str | None = Query(default=None, max_length=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """``note``: patient-reported complaints/concerns for today's visit,
    collected by the frontend's pre-generation confirm step."""
    return await _stream_kind(member_id, kind, user, db, record_id=record_id, note=note)


@router.post("/smart/stream", deprecated=True)
async def smart_report_stream(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _stream_kind(member_id, "smart_report", user, db)


@router.post("/pre-consultation/stream", deprecated=True)
async def preconsultation_stream(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _stream_kind(member_id, "pre_consultation", user, db)


@router.get("/latest")
async def latest_report(
    member_id: uuid.UUID,
    kind: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    kind = _resolve_kind(kind)
    await get_scoped_member(member_id, user, db)
    insight = await report_service.latest_report(db, member_id, kind)
    return _to_view(insight) if insight else None


@router.get("/{kind}/latest")
async def latest_report_by_kind(
    member_id: uuid.UUID,
    kind: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    return await latest_report(member_id, _resolve_kind(kind), user, db)
