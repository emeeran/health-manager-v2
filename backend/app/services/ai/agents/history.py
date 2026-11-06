"""History agent: assemble the member's whole record as an evidence index.

No model call happens here. Every row that the audit can cite is read from
the database and given a stable ``domain:uuid`` reference, so the auditor
reasons over ids and code expands them into labelled evidence afterwards.

The index is deliberately compact (labels + values + dates) — it is prompt
context, not a second copy of the chart.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    ConditionEpisode,
    FamilyMember,
    HealthRecord,
    LabResult,
    Medication,
    SymptomEntry,
    Vaccination,
    VitalMeasurement,
)

# Evidence budget: enough for a long history without blowing a local
# model's context. Rows are added in clinical priority order below.
MAX_EVIDENCE = 200
MAX_LABS = 80
MAX_VITALS = 40

# A domain counts as stale after this many days without a new entry.
STALE_DAYS = {
    "labs": 365,
    "vitals": 180,
    "visits": 365,
    "medications": 180,
}


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age(birth_date: date | None, today: date) -> int | None:
    if birth_date is None:
        return None
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )


def _row(
    domain: str,
    ref: str,
    label: str,
    value: str | None = None,
    when: str | None = None,
) -> dict:
    return {"domain": domain, "ref": ref, "label": label, "value": value, "date": when}


def _days_since(value: date | datetime | None, today: date) -> int | None:
    if value is None:
        return None
    day = value.date() if isinstance(value, datetime) else value
    return (today - day).days


async def _household_names(db: AsyncSession, household_id: uuid.UUID) -> list[str]:
    """Every name that must never reach an external search query."""
    rows = await db.scalars(select(FamilyMember).where(FamilyMember.household_id == household_id))
    return [m.name for m in rows if m.name]


def _profile_row(member: FamilyMember, today: date) -> dict:
    bits = []
    age = _age(member.birth_date, today)
    if age is not None:
        bits.append(f"age {age}")
    if member.sex:
        bits.append(member.sex)
    if member.relationship:
        bits.append(member.relationship)
    return _row(
        "profile",
        "member:profile",
        "Member profile",
        ", ".join(bits) or None,
    )


async def build_audit_context(db: AsyncSession, member_id: uuid.UUID) -> dict:
    """Full-record context for the auditor.

    Returns ``evidence`` (id-referenced rows), ``counts``/``coverage`` for
    staleness reasoning, deterministic ``gaps``, and — kept out of every
    prompt — ``household_names`` for query redaction.
    """
    member = await db.get(FamilyMember, member_id)
    if member is None:
        return {
            "member_id": str(member_id),
            "household_id": None,
            "evidence": [],
            "counts": {},
            "coverage": {},
            "gaps": [],
            "household_names": [],
            "active_medications": [],
            "profile": {},
        }

    today = datetime.now(UTC).date()
    evidence: list[dict] = []

    # 1. Profile + free-text history (always first: family history is often
    #    the only evidence for a hereditary claim).
    profile = _profile_row(member, today)
    evidence.append(profile)
    if member.medical_history:
        evidence.append(
            _row(
                "profile",
                "member:medical_history",
                "Personal medical history",
                member.medical_history[:2000],
            )
        )
    if member.family_medical_history:
        evidence.append(
            _row(
                "profile",
                "member:family_medical_history",
                "Family medical history",
                member.family_medical_history[:2000],
            )
        )
    if member.blood_group:
        evidence.append(
            _row("profile", "member:blood_group", "Blood group", member.blood_group)
        )

    conditions = list(
        await db.scalars(
            select(ConditionEpisode)
            .where(ConditionEpisode.member_id == member_id)
            .order_by(ConditionEpisode.onset_date.desc().nullslast())
            .limit(100)
        )
    )
    for condition in conditions:
        detail = condition.status
        if condition.icd10_code:
            detail = f"{detail}; ICD-10 {condition.icd10_code}"
        evidence.append(
            _row(
                "condition",
                f"condition:{condition.id}",
                condition.name,
                detail,
                _iso(condition.onset_date),
            )
        )

    medications = list(
        await db.scalars(
            select(Medication)
            .where(Medication.member_id == member_id)
            .order_by(Medication.status, Medication.start_date.desc().nullslast())
        )
    )
    active_medications: list[dict] = []
    for medication in medications:
        label = f"{medication.medicine} {medication.dosage or ''}".strip()
        detail = f"{medication.status}"
        if medication.timing:
            detail += f"; {medication.timing}"
        evidence.append(
            _row(
                "medication",
                f"medication:{medication.id}",
                label,
                detail,
                _iso(medication.start_date),
            )
        )
        if medication.status == "active":
            active_medications.append(
                {
                    "ref": f"medication:{medication.id}",
                    "medicine": medication.medicine,
                    "dosage": medication.dosage,
                }
            )

    labs = list(
        await db.scalars(
            select(LabResult)
            .where(LabResult.member_id == member_id)
            .order_by(LabResult.record_date.desc().nullslast())
            .limit(MAX_LABS)
        )
    )
    for lab in labs:
        value = lab.result if lab.result is not None else lab.value_num
        rendered = f"{value} {lab.units or ''}".strip()
        if lab.flag:
            rendered = f"{rendered} [{lab.flag}]".strip()
        evidence.append(
            _row(
                "lab",
                f"lab:{lab.id}",
                lab.test_name,
                rendered or None,
                _iso(lab.record_date),
            )
        )

    vitals = list(
        await db.scalars(
            select(VitalMeasurement)
            .where(VitalMeasurement.member_id == member_id)
            .order_by(VitalMeasurement.measured_at.desc())
            .limit(MAX_VITALS)
        )
    )
    for vital in vitals:
        value = f"{vital.value_num}"
        if vital.value_secondary is not None:
            value += f"/{vital.value_secondary}"
        if vital.unit:
            value += f" {vital.unit}"
        evidence.append(
            _row(
                "vital",
                f"vital:{vital.id}",
                vital.vital_type,
                value,
                _iso(vital.measured_at),
            )
        )

    visits = list(
        await db.scalars(
            select(HealthRecord)
            .where(
                HealthRecord.member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
            .limit(30)
        )
    )
    for visit in visits:
        evidence.append(
            _row(
                "visit",
                f"visit:{visit.id}",
                f"{visit.record_type} — {visit.doctor_name or 'clinician'}",
                (visit.diagnosis or visit.summary or "")[:600] or None,
                _iso(visit.record_date),
            )
        )

    allergies = list(
        await db.scalars(select(Allergy).where(Allergy.member_id == member_id))
    )
    for allergy in allergies:
        detail = allergy.severity
        if allergy.reaction:
            detail += f"; {allergy.reaction}"
        detail += "; verified" if allergy.verified else "; unverified"
        evidence.append(
            _row("allergy", f"allergy:{allergy.id}", allergy.substance, detail)
        )

    vaccinations = list(
        await db.scalars(
            select(Vaccination)
            .where(Vaccination.member_id == member_id)
            .order_by(Vaccination.date_administered.desc())
            .limit(30)
        )
    )
    for vaccination in vaccinations:
        evidence.append(
            _row(
                "vaccination",
                f"vaccination:{vaccination.id}",
                vaccination.name,
                "administered",
                _iso(vaccination.date_administered),
            )
        )

    symptoms = list(
        await db.scalars(
            select(SymptomEntry)
            .where(SymptomEntry.member_id == member_id, SymptomEntry.resolved_at.is_(None))
            .order_by(SymptomEntry.started_at.desc())
            .limit(20)
        )
    )
    for symptom in symptoms:
        evidence.append(
            _row(
                "symptom",
                f"symptom:{symptom.id}",
                symptom.symptom,
                f"severity {symptom.severity}",
                _iso(symptom.started_at),
            )
        )

    evidence = evidence[:MAX_EVIDENCE]

    latest_lab = _iso(labs[0].record_date) if labs and labs[0].record_date else None
    latest_vital = _iso(vitals[0].measured_at) if vitals else None
    latest_visit = _iso(visits[0].record_date) if visits else None
    latest_med = _iso(medications[0].start_date) if medications and medications[0].start_date else None

    coverage = {
        "labs": {
            "count": len(labs),
            "latest": latest_lab,
            "days_since": _days_since(labs[0].record_date, today) if labs else None,
        },
        "vitals": {
            "count": len(vitals),
            "latest": latest_vital,
            "days_since": _days_since(vitals[0].measured_at, today) if vitals else None,
        },
        "visits": {
            "count": len(visits),
            "latest": latest_visit,
            "days_since": _days_since(visits[0].record_date, today) if visits else None,
        },
        "medications": {
            "count": len(medications),
            "active": len(active_medications),
            "latest_start": latest_med,
        },
        "conditions": {"count": len(conditions)},
        "allergies": {
            "count": len(allergies),
            "unverified": sum(1 for a in allergies if not a.verified),
        },
        "vaccinations": {"count": len(vaccinations)},
        "symptoms": {"active": len(symptoms)},
    }

    gaps = compute_gaps(member, coverage)

    return {
        "member_id": str(member.id),
        "household_id": str(member.household_id),
        "evidence": evidence,
        "counts": {
            "evidence": len(evidence),
            "conditions": len(conditions),
            "medications": len(medications),
            "labs": len(labs),
            "vitals": len(vitals),
            "visits": len(visits),
        },
        "coverage": coverage,
        "gaps": gaps,
        "household_names": await _household_names(db, member.household_id),
        "active_medications": active_medications,
        "profile": {
            "age_years": _age(member.birth_date, today),
            "sex": member.sex,
            "relationship": member.relationship,
        },
    }


def compute_gaps(member: FamilyMember, coverage: dict) -> list[dict]:
    """Deterministic record-coverage gaps — authoritative, not model output."""
    gaps: list[dict] = []

    def add(domain: str, status: str, detail: str) -> None:
        gaps.append({"domain": domain, "status": status, "detail": detail})

    if not member.medical_history:
        add("history", "missing", "Personal medical history is not recorded.")
    if not member.family_medical_history:
        add("history", "missing", "Family medical history is not recorded.")

    allergies = coverage.get("allergies", {})
    if not allergies.get("count"):
        add("allergies", "missing", "No allergies are recorded.")
    elif allergies.get("unverified"):
        add(
            "allergies",
            "missing",
            f"{allergies['unverified']} recorded allergy item(s) are unverified.",
        )

    for domain, label, threshold in (
        ("labs", "Laboratory results", STALE_DAYS["labs"]),
        ("vitals", "Vital measurements", STALE_DAYS["vitals"]),
        ("visits", "Doctor visits", STALE_DAYS["visits"]),
    ):
        section = coverage.get(domain, {})
        days = section.get("days_since")
        if not section.get("count"):
            add(domain, "missing", f"{label} are not recorded.")
        elif days is not None and days > threshold:
            add(
                domain,
                "stale",
                f"Last {label.lower()} were {days} days ago (threshold {threshold}).",
            )

    if not coverage.get("vaccinations", {}).get("count"):
        add("vaccinations", "missing", "No vaccinations are recorded.")

    return gaps
