"""Smart search: NL question → DB-grounded record results.

Shape matches v1 (POST /smart-search/records {query} → {results,
ai_powered}); POST /smart-search accepts {question} as an alias. The AI's
role is deliberately narrow: it parses the question into structured
FILTERS only (member, record types, date range, keywords). Every fact in
the response comes from the database — deterministic matching runs in
Python because the PHI columns are Fernet-encrypted at rest, so the model
never sees raw rows and can never invent numbers into the result set.
"""

import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id
from app.models import FamilyMember, HealthRecord, RecordType, User
from app.services.ai import router as ai_router
from app.services.ai.extraction import parse_llm_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart-search", tags=["smart-search"])

FILTER_SYSTEM = (
    "You convert natural-language health-record searches into JSON "
    "filters. Use ONLY the household members listed in the prompt; never "
    "invent names, dates, or record types. Respond with JSON only: "
    '{"member_name": str|null, "record_types": [str], "date_from": '
    '"YYYY-MM-DD"|null, "date_to": "YYYY-MM-DD"|null, "keywords": [str]}'
)


class SmartSearchRequest(BaseModel):
    # v1 field name; {question} accepted per the v2 endpoint contract.
    query: str | None = Field(default=None, min_length=2, max_length=500)
    question: str | None = Field(default=None, min_length=2, max_length=500)

    def text(self) -> str:
        value = (self.query or self.question or "").strip()
        if len(value) < 2:
            raise HTTPException(
                422, "Provide a non-empty 'query' (or 'question') of at least 2 characters"
            )
        return value


class SmartSearchResult(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    member_name: str
    record_type: str
    record_date: str | None = None
    diagnosis: str | None = None
    preview: str | None = None


class SmartSearchResponse(BaseModel):
    results: list[SmartSearchResult]
    ai_powered: bool = False


async def _parse_filters(provider, question: str, members: list[FamilyMember]) -> dict | None:
    member_list = "; ".join(f"{m.name} ({m.relationship})" for m in members)
    prompt = (
        f"Household members: {member_list}\n\nSearch query: {question}\n\nReturn the JSON filters."
    )
    try:
        raw = await provider.complete(prompt, system=FILTER_SYSTEM, max_tokens=300)
    except Exception as exc:  # provider I/O failure → text fallback
        logger.warning("smart-search AI parse failed: %s", exc)
        return None
    parsed = parse_llm_json(raw)
    return parsed or None


def _record_matches(record: HealthRecord, terms: list[str]) -> bool:
    haystacks = [
        record.diagnosis or "",
        record.prescription_text or "",
        record.summary or "",
        record.doctor_name or "",
        json.dumps(record.clinical_data)
        if isinstance(record.clinical_data, dict)
        else (record.clinical_data or ""),
        str(record.record_type),
    ]
    hay = " ".join(haystacks).lower()
    return any(term.lower() in hay for term in terms if term)


def _preview(record: HealthRecord) -> str | None:
    if record.diagnosis:
        return record.diagnosis
    data = record.clinical_data
    if isinstance(data, dict):
        for key in ("chief_complaint", "summary"):
            if data.get(key):
                return str(data[key])
        return json.dumps(data)[:120]
    if isinstance(data, str) and data:
        return data[:120]
    return record.summary


async def _run_search(
    question: str,
    user: User,
    db: AsyncSession,
    limit: int,
) -> SmartSearchResponse:
    hid = await get_household_id(user, db)
    members = list(await db.scalars(select(FamilyMember).where(FamilyMember.household_id == hid)))
    member_map = {m.id: m for m in members}

    # Deterministic context only — the model narrates filters, never facts.
    filters: dict = {}
    ai_powered = False
    plan = await ai_router.plan_for_household(db, hid, local_only=False)
    provider = await ai_router.first_available(plan)
    if provider is not None:
        parsed = await _parse_filters(provider, question, members)
        if parsed:
            filters = parsed
            ai_powered = True

    stmt = (
        select(HealthRecord)
        .where(
            HealthRecord.member_id.in_([m.id for m in members]),
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
    )

    if ai_powered:
        member_name = str(filters.get("member_name") or "").lower().strip()
        if member_name:
            matched = [
                m.id
                for m in members
                if member_name in m.name.lower() or member_name in m.relationship.lower()
            ]
            if matched:
                stmt = stmt.where(HealthRecord.member_id.in_(matched))
        types = [
            RecordType(rt)
            for rt in filters.get("record_types") or []
            if rt in {t.value for t in RecordType}
        ]
        if types:
            stmt = stmt.where(HealthRecord.record_type.in_(types))
        for key, op in (("date_from", "__ge__"), ("date_to", "__le__")):
            raw = filters.get(key)
            if raw:
                try:
                    stmt = stmt.where(
                        getattr(HealthRecord.record_date, op)(date.fromisoformat(str(raw)))
                    )
                except ValueError:
                    pass
        search_terms = [str(k) for k in (filters.get("keywords") or []) if k]
    else:
        search_terms = [question]

    records = await db.scalars(stmt)
    results = []
    for r in records:
        if not _record_matches(r, search_terms or [question]):
            continue
        member = member_map.get(r.member_id)
        results.append(
            SmartSearchResult(
                id=r.id,
                member_id=r.member_id,
                member_name=member.name if member else "—",
                record_type=str(r.record_type),
                record_date=r.record_date.isoformat() if r.record_date else None,
                diagnosis=r.diagnosis,
                preview=_preview(r),
            )
        )
        if len(results) >= limit:
            break
    return SmartSearchResponse(results=results, ai_powered=ai_powered)


@router.post("", response_model=SmartSearchResponse)
async def smart_search_question(
    body: SmartSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=12, le=50),
) -> SmartSearchResponse:
    """NL question → grounded record results (AI parses filters only)."""
    return await _run_search(body.text(), user, db, limit)


@router.post("/records", response_model=SmartSearchResponse)
async def smart_search_records(
    body: SmartSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=12, le=50),
) -> SmartSearchResponse:
    """v1-compatible alias of POST /smart-search."""
    return await _run_search(body.text(), user, db, limit)
