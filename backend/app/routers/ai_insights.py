"""Standalone AI insights: generation (SSE or JSON), listing, read-by-id.

- GET  /api/v1/insights?member_id=&kind=   → listing (newest first)
- POST /api/v1/insights {member_id, kind, question?, stream?} → generate;
  `stream=true` answers as SSE, `stream=false` blocks and returns the view.
  `kind` is any report kind, or "health_qa" — a question answered from the
  member's computed snapshot (ground truth) plus, when the household has a
  reference index built, the local RAG grounding (citations carry metadata
  only — excerpt text never leaves the server).
- GET  /api/v1/insights/{id}               → single insight view

Verification polling rides the existing verifications router
(GET /api/v1/verifications/{id}) via `verification_id`.
"""

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.core.sse import sse_response
from app.models import Insight, User
from app.services import report_service
from app.services.ai import router as ai_router
from app.services.ai.verification import pick_verifiers
from app.services.insight_service import (
    CITATION_CONVENTION,
    CLINICAL_WRITING_STYLE,
    INSIGHT_ANSWER_SCHEMA_TITLE,
    JSON_HARD_RULES,
    InsightAnswer,
    grounded_reference_block,
    render_schema_block,
)

router = APIRouter(prefix="/insights", tags=["insights"])

QA_KIND = "health_qa"
VALID_KINDS = (*report_service.SNAPSHOT_BUILDERS, QA_KIND)


class InsightCreate(BaseModel):
    member_id: uuid.UUID
    kind: str
    question: str | None = Field(default=None, max_length=2000)
    stream: bool = True


def insight_view(insight: Insight) -> dict:
    return {
        "id": str(insight.id),
        "member_id": str(insight.member_id),
        "kind": insight.kind,
        "content": insight.content,
        "sources": json.loads(insight.sources_json) if insight.sources_json else None,
        "verification_id": str(insight.verification_id) if insight.verification_id else None,
        "provider_used": insight.provider_used,
        "created_at": insight.created_at.isoformat(),
    }


def _qa_prompt(question: str, stats: dict, rag_block: str) -> str:
    prompt = (
        "You are answering a health question about a family member using "
        "ONLY their recorded data. Question:\n"
        f"{question}\n\n"
        "Member data (ground truth — computed from the records):\n"
        f"{json.dumps(stats, ensure_ascii=False, indent=1, default=str)}\n\n"
    )
    if rag_block:
        prompt += f"{rag_block}\n\n"
    prompt += (
        render_schema_block(InsightAnswer, title=INSIGHT_ANSWER_SCHEMA_TITLE)
        + "\n\n"
        + JSON_HARD_RULES
    )
    return prompt


def _qa_narrative(raw: str) -> str:
    """Readable prose for the auditor — the QA payload itself is JSON."""
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(data, dict):
        return raw
    parts = [str(data.get("headline") or ""), str(data.get("narrative") or "")]
    parts.extend(f"- {item}" for item in data.get("key_findings") or [])
    parts.extend(f"Recommendation: {item}" for item in data.get("recommendations") or [])
    return "\n".join(part for part in parts if part)


async def qa_stream(
    db: AsyncSession,
    member_id: uuid.UUID,
    question: str,
    provider,
    verifier,
) -> AsyncIterator[dict]:
    """Question insight: snapshot + optional grounding → one JSON answer."""
    from app.services.ai.verification import schedule_audit

    yield {"stage": "stats", "message": "collecting member statistics"}
    stats = await report_service.collect_stats(db, member_id)
    rag_block, citations = grounded_reference_block(question)
    if rag_block:
        yield {"stage": "grounding", "message": "local reference excerpts attached"}

    prompt = _qa_prompt(question, stats, rag_block)
    yield {"stage": "narrating", "message": "AI answering"}
    raw = await provider.complete(
        prompt,
        system=CLINICAL_WRITING_STYLE + CITATION_CONVENTION + JSON_HARD_RULES,
    )
    # The answer must parse into the same Pydantic model the prompt rendered;
    # a payload that fails validation is still persisted (flagged) so the
    # client sees what the model wrote rather than losing it.
    structured_ok = True
    try:
        InsightAnswer.model_validate_json(raw)
    except Exception:  # noqa: BLE001 — validation errors are recorded, not fatal
        structured_ok = False

    verification_id = None
    if verifier:
        yield {"stage": "verifying", "message": "auditing claims"}
        verification_id = await schedule_audit(
            db,
            member_id,
            f"insight:{QA_KIND}",
            _qa_narrative(raw),
            verifier,
            kind=QA_KIND,
            commit=False,
        )

    insight = Insight(
        member_id=member_id,
        kind=QA_KIND,
        content=raw,
        sources_json=json.dumps(
            {
                "question": question,
                "ground_truth_stats": stats,
                "citations": citations,
                "structured_ok": structured_ok,
            },
            ensure_ascii=False,
            default=str,
        ),
        verification_id=verification_id,
        provider_used=getattr(provider, "name", "unknown"),
    )
    db.add(insight)
    await db.commit()
    yield {"stage": "complete", "report": insight_view(insight)}


async def resolve_ai_provider(member_id, user, db):
    """Scoped member → consent-gated plan → first provider (+ verifier).

    Shared with the reports router, which serves the same snapshot kinds."""
    member = await get_scoped_member(member_id, user, db)
    plan = ai_router.build_plan(local_only=not member.cloud_ai_consent)
    provider = await ai_router.first_available(plan)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider available")
    verifier = (
        pick_verifiers(plan, str(getattr(provider, "name", "")))
        if get_settings().AI_VERIFICATION_ENABLED
        else None
    )
    return provider, verifier


@router.get("")
async def list_insights(
    member_id: uuid.UUID | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if member_id:
        await get_scoped_member(member_id, user, db)
    filters = []
    if member_id:
        filters.append(Insight.member_id == member_id)
    if kind:
        filters.append(Insight.kind == kind)
    rows = await db.scalars(
        select(Insight).where(*filters).order_by(Insight.created_at.desc()).limit(limit)
    )
    return [insight_view(r) for r in rows]


@router.post("")
async def create_insight(
    body: InsightCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.kind not in VALID_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown insight kind")
    question = (body.question or "").strip()
    if body.kind == QA_KIND and not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "health_qa requires a question")
    provider, verifier = await resolve_ai_provider(body.member_id, user, db)
    if body.kind == QA_KIND:
        source = qa_stream(db, body.member_id, question, provider, verifier)
    else:
        source = report_service.report_stream(db, body.member_id, body.kind, provider, verifier)
    if body.stream:
        return sse_response(source)
    async for event in source:
        if event.get("stage") == "complete":
            return JSONResponse(event["report"])
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Insight generation produced no result")


@router.get("/{insight_id}")
async def get_insight(
    insight_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    insight = await db.get(Insight, insight_id)
    if insight is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Insight not found")
    await get_scoped_member(insight.member_id, user, db)
    return insight_view(insight)
