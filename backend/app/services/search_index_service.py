"""Cross-member full-text search (Phase 10, ported from v1 Wave 3.8).

v1 scored BM25 in Python for SQLite/Postgres portability; v2 is
aiosqlite-only, so we use real FTS5 (bm25() ranking + snippet()) backed
by the plaintext ``search_mirror`` table. The mirror is derived state:
``reindex_all`` rebuilds it entirely from the domain tables. There is no
per-write hook in this slice — the search router exposes
``POST /api/v1/search/reindex`` for on-demand rebuilds (full rebuild is
correct and single-digit-milliseconds fast at family scale).
"""

import json
import logging
import re
import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    ConditionEpisode,
    FamilyMember,
    HealthRecord,
    LabResult,
    Medication,
    SymptomEntry,
    VitalMeasurement,
)
from app.models.search_mirror import SearchMirror

logger = logging.getLogger(__name__)

FTS_TABLE = "search_fts"

# Mirror digest cap — a digest, not a full PHI dump.
_DIGEST_MAX_CHARS = 4000

# Vaccinations are deliberately not mirrored: their searchable surface
# (name / booster dates) is served by the dashboard's vaccination_status.


def _fts_create_ddl() -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5("
        "title, body, row_id UNINDEXED, member_id UNINDEXED, "
        "household_id UNINDEXED, row_type UNINDEXED)"
    )


async def ensure_fts(db: AsyncSession) -> None:
    """Create the FTS5 virtual table if it does not exist yet.

    SQLAlchemy models can't express virtual tables for create_all, so the
    index is ensured lazily at query/reindex time.
    """
    await db.execute(text(_fts_create_ddl()))


def _clinical_summary(clinical_data: str | dict | None) -> str:
    """Human-readable digest of a record's structured clinical_data JSON."""
    if not clinical_data:
        return ""
    if isinstance(clinical_data, str):
        try:
            parsed = json.loads(clinical_data)
        except ValueError:
            return clinical_data[:200]
    else:
        parsed = clinical_data
    if not isinstance(parsed, dict):
        return ""
    parts: list[str] = []
    for key, value in parsed.items():
        if value is None:
            continue
        if isinstance(value, dict):
            inner = ", ".join(f"{k}: {v}" for k, v in value.items() if v is not None)
            parts.append(f"{key}: {inner}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("medicine") or item.get("test_name") or ""
                    detail = str(item.get("dosage") or item.get("result") or "")
                    parts.append(f"{key}: {name} {detail}".strip())
                else:
                    parts.append(f"{key}: {item}")
        else:
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


def _record_doc(record: HealthRecord) -> tuple[str, str]:
    parts: list[str] = [str(record.record_type)]
    for field in (
        record.diagnosis,
        record.prescription_text,
        record.doctor_name,
        record.summary,
    ):
        if field:
            parts.append(str(field))
    summary = _clinical_summary(record.clinical_data)
    if summary:
        parts.append(summary)
    body = " ".join(p for p in parts if p)[:_DIGEST_MAX_CHARS]
    title = str(record.diagnosis or record.summary or record.record_type)[:300]
    return title, body


async def _member_ids_for_household(db: AsyncSession, household_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(FamilyMember.id).where(FamilyMember.household_id == household_id)
    )
    return list(rows)


async def reindex_all(db: AsyncSession, household_id: uuid.UUID | None = None) -> int:
    """Full mirror + FTS rebuild from the domain tables.

    Scoped to one household when given (the router always passes one —
    mirrors are household-partitioned). Returns rows indexed. Rebuild-all
    per household is deliberate: the derived mirror is small at family
    scale and rebuild guarantees correctness without write hooks.
    """
    await ensure_fts(db)
    if household_id is None:
        await db.execute(sa_delete(SearchMirror))
        await db.execute(text(f"DELETE FROM {FTS_TABLE}"))
        household_ids = list(await db.scalars(select(FamilyMember.household_id).distinct()))
        count = 0
        for hid in household_ids:
            count += await _reindex_household(db, hid)
        await db.flush()
        return count
    count = await _reindex_household(db, household_id)
    await db.flush()
    return count


async def _reindex_household(db: AsyncSession, household_id: uuid.UUID) -> int:
    await db.execute(sa_delete(SearchMirror).where(SearchMirror.household_id == household_id))
    await db.execute(
        text(f"DELETE FROM {FTS_TABLE} WHERE household_id = :hh"),
        {"hh": str(household_id)},
    )
    member_ids = await _member_ids_for_household(db, household_id)
    if not member_ids:
        return 0
    count = 0

    async def _add(row_type: str, row_id, member_id, title: str, body: str) -> None:
        nonlocal count
        db.add(
            SearchMirror(
                row_type=row_type,
                row_id=row_id,
                member_id=member_id,
                household_id=household_id,
                title=title[:300],
                body=body[:_DIGEST_MAX_CHARS],
            )
        )
        await db.execute(
            text(
                f"INSERT INTO {FTS_TABLE} "
                "(title, body, row_id, member_id, household_id, row_type) "
                "VALUES (:title, :body, :row_id, :member_id, :household_id, :row_type)"
            ),
            {
                "title": title,
                "body": body,
                "row_id": str(row_id),
                "member_id": str(member_id),
                "household_id": str(household_id),
                "row_type": row_type,
            },
        )
        count += 1

    records = (
        await db.scalars(
            select(HealthRecord).where(
                HealthRecord.member_id.in_(member_ids),
                HealthRecord.is_deleted.is_(False),
                HealthRecord.merged_into_id.is_(None),
            )
        )
    ).all()
    for r in records:
        title, body = _record_doc(r)
        await _add("record", r.id, r.member_id, title, body)

    meds = (await db.scalars(select(Medication).where(Medication.member_id.in_(member_ids)))).all()
    for m in meds:
        body_parts = [
            p
            for p in (
                m.medicine,
                m.dosage,
                m.timing,
                m.status,
                m.notes or "",
            )
            if p
        ]
        await _add("medication", m.id, m.member_id, m.medicine, " ".join(body_parts))

    labs = (await db.scalars(select(LabResult).where(LabResult.member_id.in_(member_ids)))).all()
    for lab in labs:
        body_parts = [
            p
            for p in (
                lab.test_name,
                lab.result or "",
                lab.units or "",
                lab.ref_value or "",
                lab.flag or "",
                lab.note or "",
            )
            if p
        ]
        await _add("lab", lab.id, lab.member_id, lab.test_name, " ".join(body_parts))

    vitals = (
        await db.scalars(select(VitalMeasurement).where(VitalMeasurement.member_id.in_(member_ids)))
    ).all()
    for v in vitals:
        value = f"{v.value_num}/{v.value_secondary}" if v.value_secondary else str(v.value_num)
        title = f"{v.vital_type} {value}"
        day = v.measured_at.date().isoformat() if v.measured_at else ""
        await _add("vital", v.id, v.member_id, title, f"{title} {v.unit or ''} {day}")

    conditions = (
        await db.scalars(select(ConditionEpisode).where(ConditionEpisode.member_id.in_(member_ids)))
    ).all()
    for c in conditions:
        body = " ".join(p for p in (c.name, c.icd10_code, c.status, c.notes or "") if p)
        await _add("condition", c.id, c.member_id, c.name, body)

    allergies = (await db.scalars(select(Allergy).where(Allergy.member_id.in_(member_ids)))).all()
    for a in allergies:
        body = " ".join(p for p in (a.substance, a.severity, a.reaction or "") if p)
        await _add("allergy", a.id, a.member_id, a.substance, body)

    symptoms = (
        await db.scalars(select(SymptomEntry).where(SymptomEntry.member_id.in_(member_ids)))
    ).all()
    for s in symptoms:
        body = " ".join(
            p
            for p in (
                s.symptom,
                s.severity,
                s.notes or "",
                s.started_at.isoformat() if s.started_at else "",
            )
            if p
        )
        await _add("symptom", s.id, s.member_id, s.symptom, body)

    return count


def fts_match_query(q: str) -> str:
    """Quote tokens so user input can't inject FTS5 query syntax."""
    tokens = re.findall(r"[\w]+", q.lower(), flags=re.UNICODE)
    return " ".join(f'"{t}"' for t in tokens)


async def search(
    db: AsyncSession,
    household_id: uuid.UUID,
    q: str,
    member_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[dict]:
    """BM25-ranked hits across the household's mirror (FTS5)."""
    match = fts_match_query(q)
    if not match:
        return []
    await ensure_fts(db)
    sql = text(
        f"SELECT row_id, member_id, row_type, title, "
        f"bm25({FTS_TABLE}) AS score, "
        f"snippet({FTS_TABLE}, 1, '<b>', '</b>', '…', 12) AS snip "
        f"FROM {FTS_TABLE} "
        f"WHERE {FTS_TABLE} MATCH :match AND household_id = :hh"
        + (" AND member_id = :mid" if member_id else "")
        + " ORDER BY score LIMIT :lim"
    )
    params: dict = {"match": match, "hh": str(household_id), "lim": limit}
    if member_id:
        params["mid"] = str(member_id)
    rows = (await db.execute(sql, params)).all()

    names: dict[str, str] = {}
    if rows:
        member_rows = await db.execute(
            select(FamilyMember.id, FamilyMember.name).where(
                FamilyMember.household_id == household_id
            )
        )
        names = {str(mid): name for mid, name in member_rows.all()}

    results = []
    for row_id, mid, row_type, _title, score, snip in rows:
        results.append(
            {
                "row_type": row_type,
                "row_id": str(row_id),
                "member_id": mid,
                "member_name": names.get(mid, "—"),
                # bm25() is negative-better; expose positive-better like v1.
                "title": _title,
                "snippet": snip,
                "score": round(-float(score), 3),
            }
        )
    return results
