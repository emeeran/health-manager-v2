"""Symptom journal router — CRUD + the correlation endpoint.

  POST   /members/{id}/symptoms                     log an entry
  GET    /members/{id}/symptoms                     list (newest onset first)
  PATCH  /members/{id}/symptoms/{entry_id}          edit (mark resolved, …)
  DELETE /members/{id}/symptoms/{entry_id}          remove
  GET    /members/{id}/symptoms/correlations        timeline correlation view

Correlation joins the occurrences of one symptom against what else was
happening to the member around each onset: concurrently active
medications and abnormal lab results within ±7 days. Counts are
descriptive context for a human — never causal claims.
"""

import uuid
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import LabResult, Medication, User
from app.models.symptom import SymptomEntry, SymptomSeverity
from app.schemas.symptom import SymptomCreate, SymptomResponse, SymptomUpdate

router = APIRouter(prefix="/members/{member_id}/symptoms", tags=["symptoms"])

# Correlation window: a lab drawn within ±7 days of onset counts as "around
# the same time" — symptoms rarely get labs drawn the same day.
CORRELATION_LAB_WINDOW_DAYS = 7


@router.post("", response_model=SymptomResponse, status_code=status.HTTP_201_CREATED)
async def create_symptom(
    member_id: uuid.UUID,
    body: SymptomCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SymptomEntry:
    await get_scoped_member(member_id, user, db)
    entry = SymptomEntry(
        member_id=member_id,
        symptom=body.symptom.strip().lower(),
        severity=body.severity.value,
        started_at=body.started_at,
        resolved_at=body.resolved_at,
        notes=body.notes,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("", response_model=list[SymptomResponse])
async def list_symptoms(
    member_id: uuid.UUID,
    symptom: str | None = Query(default=None, description="Filter to one symptom key"),
    limit: int = Query(default=100, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SymptomEntry]:
    await get_scoped_member(member_id, user, db)
    query = (
        select(SymptomEntry)
        .where(SymptomEntry.member_id == member_id)
        .order_by(SymptomEntry.started_at.desc(), SymptomEntry.created_at.desc())
        .limit(limit)
    )
    if symptom:
        query = query.where(SymptomEntry.symptom == symptom.strip().lower())
    return list(await db.scalars(query))


async def _get_entry(db: AsyncSession, member_id: uuid.UUID, entry_id: uuid.UUID) -> SymptomEntry:
    entry = await db.get(SymptomEntry, entry_id)
    if entry is None or entry.member_id != member_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Symptom entry not found")
    return entry


@router.patch("/{entry_id}", response_model=SymptomResponse)
async def update_symptom(
    member_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: SymptomUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SymptomEntry:
    await get_scoped_member(member_id, user, db)
    entry = await _get_entry(db, member_id, entry_id)
    updates = body.model_dump(exclude_unset=True)
    if "symptom" in updates and updates["symptom"] is not None:
        updates["symptom"] = updates["symptom"].strip().lower()
    for field, value in updates.items():
        setattr(entry, field, value.value if hasattr(value, "value") else value)
    if entry.resolved_at and entry.started_at and entry.resolved_at < entry.started_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "resolved_at cannot precede started_at",
        )
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_symptom(
    member_id: uuid.UUID,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_scoped_member(member_id, user, db)
    entry = await _get_entry(db, member_id, entry_id)
    await db.delete(entry)
    await db.flush()


@router.get("/correlations")
async def symptom_correlations(
    member_id: uuid.UUID,
    symptom: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What else was happening around each occurrence of this symptom?

    Descriptive co-occurrence only — the response says so, because
    correlation counts are context for a conversation with a doctor,
    not causes.
    """
    await get_scoped_member(member_id, user, db)
    key = symptom.strip().lower()
    entries = list(
        await db.scalars(
            select(SymptomEntry)
            .where(SymptomEntry.member_id == member_id)
            .where(SymptomEntry.symptom == key)
            .order_by(SymptomEntry.started_at)
        )
    )
    if not entries:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No entries logged for that symptom")

    onsets = [e.started_at for e in entries]

    # Concurrently active medications: start ≤ onset, still within (or
    # without) an end date.
    meds = list(
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member_id,
                Medication.status == "active",
            )
        )
    )
    med_hits: Counter[str] = Counter()
    for onset in onsets:
        for m in meds:
            if m.start_date is None or m.start_date > onset:
                continue
            if m.end_date is not None and m.end_date < onset:
                continue
            med_hits[m.medicine] += 1

    # Abnormal labs near onset (± CORRELATION_LAB_WINDOW_DAYS).
    lab_hits: Counter[str] = Counter()
    if onsets:
        lab_window_start = min(onsets) - timedelta(days=CORRELATION_LAB_WINDOW_DAYS)
        lab_window_end = max(onsets) + timedelta(days=CORRELATION_LAB_WINDOW_DAYS)
        labs = list(
            await db.scalars(
                select(LabResult).where(
                    LabResult.member_id == member_id,
                    LabResult.record_date >= lab_window_start,
                    LabResult.record_date <= lab_window_end,
                    LabResult.flag.is_not(None),
                )
            )
        )
        for onset in onsets:
            for lab in labs:
                if (
                    lab.record_date
                    and abs((lab.record_date - onset).days) <= CORRELATION_LAB_WINDOW_DAYS
                ):
                    lab_hits[lab.test_name] += 1

    # Co-occurring symptom keys (logged within ±3 days of an onset).
    symptom_hits: Counter[str] = Counter()
    others = list(
        await db.scalars(
            select(SymptomEntry)
            .where(SymptomEntry.member_id == member_id)
            .where(SymptomEntry.symptom != key)
        )
    )
    for onset in onsets:
        for other in others:
            if other.started_at and abs((other.started_at - onset).days) <= 3:
                symptom_hits[other.symptom] += 1

    def _rank(counter: Counter[str]) -> list[dict]:
        return [
            {"name": name, "count": count, "of": len(onsets)}
            for name, count in counter.most_common()
        ]

    return {
        "symptom": key,
        "occurrences": len(onsets),
        "first_seen": min(onsets).isoformat(),
        "last_seen": max(onsets).isoformat(),
        "severity_counts": {
            sev.value: sum(1 for e in entries if e.severity == sev.value) for sev in SymptomSeverity
        },
        "with_medications": _rank(med_hits),
        "with_abnormal_labs": _rank(lab_hits),
        "co_occurring_symptoms": _rank(symptom_hits),
        "disclaimer": "Co-occurrence, not causation — bring this to your doctor.",
    }
