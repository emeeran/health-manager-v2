"""Preventive-care recommendation engine.

Deterministic rules over age / sex / active conditions / latest vitals — no
AI, works offline. Core rule set only (screenings + vaccinations); dismissal
persistence lives in the PreventiveDismissal model.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.condition import ConditionEpisode
from app.models.member import FamilyMember
from app.models.preventive import PreventiveDismissal
from app.models.vital import VitalMeasurement


# Sex restriction on a rule: None = all, else "male"/"female".
@dataclass(frozen=True)
class AgeRuleSpec:
    min_age: int
    max_age: int | None
    sex: str | None
    title: str
    detail: str
    category: str


# Keep tight and actionable — no filler.
AGE_RULES: tuple[AgeRuleSpec, ...] = (
    AgeRuleSpec(
        0, 5, None, "Well-Child Visits", "Regular growth and development checks", "screening"
    ),
    AgeRuleSpec(
        0, 6, None, "Childhood Immunizations", "Routine schedule catch-up review", "vaccination"
    ),
    AgeRuleSpec(3, 18, None, "Vision Screening", "Visual acuity check", "screening"),
    AgeRuleSpec(
        0, None, None, "Annual Flu Vaccine", "Influenza immunization (6 months+)", "vaccination"
    ),
    AgeRuleSpec(9, 26, None, "HPV Vaccine", "If unvaccinated — through age 26", "vaccination"),
    AgeRuleSpec(18, None, None, "Annual Physical Exam", "General health check-up", "screening"),
    AgeRuleSpec(
        18, None, None, "Blood Pressure Screening", "Check at every health visit", "screening"
    ),
    AgeRuleSpec(
        18, None, None, "Dental Check-up", "Oral health examination and cleaning", "screening"
    ),
    AgeRuleSpec(18, None, None, "Tetanus Booster (Td/Tdap)", "Every 10 years", "vaccination"),
    AgeRuleSpec(21, 65, "female", "Cervical Cancer Screening", "Pap smear / HPV test", "screening"),
    AgeRuleSpec(30, None, None, "Lipid Profile", "Cholesterol and triglycerides", "lab"),
    AgeRuleSpec(
        35, None, None, "Diabetes Screening (HbA1c)", "Every 3 years if non-diabetic", "lab"
    ),
    AgeRuleSpec(
        40, None, None, "Comprehensive Metabolic Panel", "Kidney and liver function", "lab"
    ),
    AgeRuleSpec(
        45, 75, None, "Colorectal Cancer Screening", "Colonoscopy or FIT test", "screening"
    ),
    AgeRuleSpec(
        50, 74, "female", "Breast Cancer Screening", "Mammogram every 2 years", "screening"
    ),
    AgeRuleSpec(
        50,
        None,
        "male",
        "Prostate Screening Discussion",
        "PSA discussion with your clinician",
        "screening",
    ),
    AgeRuleSpec(65, None, "female", "Bone Density (DEXA)", "Osteoporosis screening", "screening"),
    AgeRuleSpec(65, None, None, "Pneumococcal Vaccine", "PCV20 or PPSV23 at 65+", "vaccination"),
    AgeRuleSpec(
        65, None, None, "Shingles Vaccine", "Two-dose series for adults 65+", "vaccination"
    ),
)

# (condition keyword, title, detail, category)
CONDITION_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("diabetes", "HbA1c Test (every 3 months)", "Glycemic control monitoring", "lab"),
    ("diabetes", "Diabetic Eye Exam", "Retinopathy screening", "screening"),
    ("diabetes", "Diabetic Foot Exam", "Neuropathy and ulcer check", "screening"),
    ("hypertension", "Kidney Function Test", "Serum creatinine and eGFR", "lab"),
    ("hypertension", "Quarterly BP Check", "Treatment efficacy monitoring", "screening"),
    ("cholesterol", "Lipid Profile (every 6 months)", "Treatment response monitoring", "lab"),
    ("thyroid", "Thyroid Function (TSH/T3/T4)", "Thyroid disorder monitoring", "lab"),
    ("asthma", "Pulmonary Function Test", "Spirometry monitoring", "lab"),
    ("depression", "Mental Health Follow-up", "Assessment and medication review", "screening"),
)

_slug_re = re.compile(r"[^a-z0-9]+")


def rec_key_for(title: str) -> str:
    """Stable slug identity of a rule — rules are literals, so this persists."""
    return _slug_re.sub("-", title.lower()).strip("-")


def age_of(member: FamilyMember) -> int | None:
    """Age in whole years from birth_date, or None when unknown."""
    if member.birth_date is None:
        return None
    today = member.birth_date.today()
    return (
        today.year
        - member.birth_date.year
        - ((today.month, today.day) < (member.birth_date.month, member.birth_date.day))
    )


async def _condition_keywords(db: AsyncSession, member: FamilyMember) -> str:
    """Lowercase blob of the member's problem list + medical-history text."""
    rows = await db.scalars(
        select(ConditionEpisode.name).where(
            ConditionEpisode.member_id == member.id,
            ConditionEpisode.status.in_(("active", "chronic")),
        )
    )
    parts = [str(r) for r in rows if r]
    history = getattr(member, "medical_history", None)
    if history:
        parts.append(str(history))
    return " ".join(parts).lower()


async def _vital_flags(db: AsyncSession, member_id: uuid.UUID) -> list[tuple[str, str]]:
    """(key, title) flags driven by the latest vitals: high BP, high HbA1c."""
    flags: list[tuple[str, str]] = []
    latest = {}
    rows = await db.scalars(
        select(VitalMeasurement)
        .where(
            VitalMeasurement.member_id == member_id,
            VitalMeasurement.vital_type.in_(("blood_pressure", "hba1c")),
        )
        .order_by(VitalMeasurement.measured_at.desc())
        .limit(20)
    )
    for row in rows:
        if row.vital_type not in latest:  # first hit per type is the latest
            latest[row.vital_type] = row
    bp = latest.get("blood_pressure")
    if bp is not None and bp.value_num >= 140:
        flags.append(("blood-pressure-recheck", "Blood Pressure Recheck"))
    hba1c = latest.get("hba1c")
    if hba1c is not None and hba1c.value_num >= 6.5:
        flags.append(("glycemic-follow-up", "Glycemic Follow-up"))
    return flags


async def generate_recommendations(db: AsyncSession, member: FamilyMember) -> list[dict]:
    """Deterministic recommendations for one member, dismissals filtered out.

    Returns [{key, title, detail, category, due}] sorted by category then
    title. Every returned rec is currently due — the dismissal table is what
    removes one.
    """
    age = age_of(member)
    sex = (member.sex or "").lower() or None
    recs: dict[str, dict] = {}

    def _add(key: str, title: str, detail: str, category: str) -> None:
        if key not in recs:
            recs[key] = {
                "key": key,
                "title": title,
                "detail": detail,
                "category": category,
                "due": True,
            }

    if age is not None:
        for rule in AGE_RULES:
            if age < rule.min_age:
                continue
            if rule.max_age is not None and age > rule.max_age:
                continue
            if rule.sex is not None and rule.sex != sex:
                continue
            _add(rec_key_for(rule.title), rule.title, rule.detail, rule.category)

    conditions_blob = await _condition_keywords(db, member)
    if conditions_blob:
        for keyword, title, detail, category in CONDITION_RULES:
            if keyword in conditions_blob:
                _add(rec_key_for(title), title, detail, category)

    for key, title in await _vital_flags(db, member.id):
        _add(key, title, "Latest reading above threshold — recheck soon", "screening")

    dismissed = await get_active_dismissals(db, member.id)
    return sorted(
        (rec for key, rec in recs.items() if key not in dismissed),
        key=lambda r: (r["category"], r["title"]),
    )


# ── dismissals ───────────────────────────────────────────────────────


async def get_active_dismissals(db: AsyncSession, member_id: uuid.UUID) -> frozenset[str]:
    """Rec keys currently hidden for the member."""
    rows = await db.scalars(
        select(PreventiveDismissal.rec_key).where(PreventiveDismissal.member_id == member_id)
    )
    return frozenset(rows)


async def dismiss(
    db: AsyncSession, member_id: uuid.UUID, rec_key: str, note: str | None = None
) -> dict:
    """Hide a recommendation (upsert — re-dismissing refreshes the row)."""
    row = (
        await db.execute(
            select(PreventiveDismissal).where(
                PreventiveDismissal.member_id == member_id,
                PreventiveDismissal.rec_key == rec_key,
            )
        )
    ).scalar_one_or_none()
    dismissed_at = datetime.now(timezone.utc)
    if row is None:
        row = PreventiveDismissal(
            member_id=member_id,
            rec_key=rec_key,
            dismissed_at=dismissed_at,
            note=note,
        )
        db.add(row)
    else:
        row.dismissed_at = dismissed_at
        if note is not None:
            row.note = note
    await db.flush()
    return {"key": rec_key, "dismissed": True}


async def undismiss(db: AsyncSession, member_id: uuid.UUID, rec_key: str) -> bool:
    """Undo a dismissal. True when a row was actually removed."""
    row = (
        await db.execute(
            select(PreventiveDismissal).where(
                PreventiveDismissal.member_id == member_id,
                PreventiveDismissal.rec_key == rec_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True
