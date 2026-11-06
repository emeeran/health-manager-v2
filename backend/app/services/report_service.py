"""Member reports: deterministic snapshots + AI narrative, stored as insights.

Every kind follows the same invariant — the model narrates, it never
invents numbers: a per-kind snapshot builder assembles the ground truth
deterministically from meds/labs/vitals/conditions in code (statistics,
counts, projections), then ONE narrative call writes prose on top of
those computed facts. Shared prompt standards come from
``app.services.insight_service``.

Kinds: smart_report, health_insights, pre_consultation, consultant_note,
consolidated_report, medication_report, medication_schedule, forecast.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from statistics import linear_regression

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    ConditionEpisode,
    FamilyMember,
    HealthRecord,
    Insight,
    LabResult,
    Medication,
    SymptomEntry,
    Vaccination,
    VitalMeasurement,
)
from app.services.dosing import expand_day
from app.services.insight_service import (
    CITATION_CONVENTION,
    CLINICAL_WRITING_STYLE,
)

REPORT_SYSTEM = (
    "You are a clinical writer preparing a health summary for a family. "
    "Use ONLY the statistics provided — never invent values. Be clear, "
    "calm, and actionable; recommend professional care for red flags.\n\n"
    "FORMAT: clean GitHub-flavored Markdown — headings, bullet lists, and "
    "tables where they aid scanning. It renders in the app's report view.\n\n"
    + CLINICAL_WRITING_STYLE
    + CITATION_CONVENTION
)


async def _active_meds(db: AsyncSession, member_id: uuid.UUID) -> list[Medication]:
    return list(
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member_id, Medication.status == "active"
            )
        )
    )


async def _recent_labs(db: AsyncSession, member_id: uuid.UUID, limit: int = 30):
    return list(
        await db.scalars(
            select(LabResult)
            .where(LabResult.member_id == member_id)
            .order_by(LabResult.record_date.desc().nullslast())
            .limit(limit)
        )
    )


async def _recent_vitals(db: AsyncSession, member_id: uuid.UUID, days: int = 90, limit: int = 30):
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    return list(
        await db.scalars(
            select(VitalMeasurement)
            .where(
                VitalMeasurement.member_id == member_id,
                VitalMeasurement.measured_at >= since,
            )
            .order_by(VitalMeasurement.measured_at.desc())
            .limit(limit)
        )
    )


def _flagged_labs(labs) -> list[dict]:
    return [
        {
            "test_name": lab.test_name,
            "result": lab.result,
            "units": lab.units,
            "flag": lab.flag,
            "record_date": lab.record_date.isoformat() if lab.record_date else None,
        }
        for lab in labs
        if lab.flag in ("low", "high")
    ]


async def _member_name(db: AsyncSession, member_id: uuid.UUID) -> str:
    member = await db.get(FamilyMember, member_id)
    return member.name if member else "Unknown"


def _age_years(birth_date: date | None, today: date) -> int | None:
    if birth_date is None:
        return None
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )


def _lab_reference_range(lab: LabResult) -> str | None:
    """Reference range as recorded — the text field wins over parsed bounds."""
    if lab.ref_value:
        return lab.ref_value
    low, high = lab.ref_low_num, lab.ref_high_num
    if low is not None and high is not None:
        return f"{low:g}-{high:g}"
    if low is not None:
        return f">={low:g}"
    if high is not None:
        return f"<={high:g}"
    return None


def _lab_point(lab: LabResult) -> dict:
    return {
        "date": lab.record_date.isoformat() if lab.record_date else None,
        "result": lab.result if lab.result is not None else lab.value_num,
        "value_num": lab.value_num,
        "units": lab.units,
        "flag": lab.flag,
        "reference_range": _lab_reference_range(lab),
    }


def _lab_trends(labs: list[LabResult], limit: int = 40) -> dict[str, dict]:
    """Latest + previous point per test, newest first — computed in code.

    The narrative quotes ``previous`` and ``delta_num``; it never has to
    recompute a trend or guess a prior date.
    """
    grouped: dict[str, list[LabResult]] = {}
    for lab in labs:  # already newest first
        if lab.record_date is None:
            continue
        grouped.setdefault(lab.test_name, []).append(lab)

    trends: dict[str, dict] = {}
    for test, rows in list(grouped.items())[:limit]:
        rows.sort(key=lambda r: r.record_date or date.min, reverse=True)
        latest = rows[0]
        prior = rows[1] if len(rows) > 1 else None
        delta = None
        if latest.value_num is not None and prior is not None and prior.value_num is not None:
            delta = round(latest.value_num - prior.value_num, 4)
        trends[test] = {
            "latest": _lab_point(latest),
            "previous": _lab_point(prior) if prior else None,
            "delta_num": delta,
        }
    return trends


async def collect_stats(db: AsyncSession, member_id: uuid.UUID) -> dict:
    """Deterministic statistics that anchor the narrative (ground truth)."""
    member_name = await _member_name(db, member_id)
    meds = await _active_meds(db, member_id)
    labs = await _recent_labs(db, member_id)
    vitals = await _recent_vitals(db, member_id)
    conditions = list(
        await db.scalars(
            select(ConditionEpisode).where(
                ConditionEpisode.member_id == member_id,
                ConditionEpisode.status != "resolved",
            )
        )
    )
    return {
        "member": member_name,
        "medications_count": len(meds),
        "medications": [f"{m.medicine} {m.dosage or ''}".strip() for m in meds],
        "labs_flagged": _flagged_labs(labs),
        "vitals_flagged": [
            {
                "vital_type": v.vital_type,
                "value_num": v.value_num,
                "value_secondary": v.value_secondary,
                "measured_at": v.measured_at.isoformat(),
            }
            for v in vitals
            if v.vital_type == "blood_pressure" and v.value_num >= 140
        ],
        "conditions_count": len(conditions),
        "conditions": [c.name for c in conditions],
    }


# ── Per-kind snapshot builders (deterministic data assembly) ─────────────────


async def snapshot_pre_consultation(db, member_id) -> dict:
    stats = await collect_stats(db, member_id)
    symptoms = list(
        await db.scalars(
            select(SymptomEntry)
            .where(SymptomEntry.member_id == member_id, SymptomEntry.resolved_at.is_(None))
            .order_by(SymptomEntry.started_at.desc())
            .limit(10)
        )
    )
    stats["active_symptoms"] = [
        {
            "symptom": s.symptom,
            "severity": s.severity,
            "started_at": s.started_at.isoformat(),
        }
        for s in symptoms
    ]
    return stats


async def snapshot_consultant_note(db, member_id) -> dict:
    """One-page consultant snapshot: active problems, regimen, key flags."""
    stats = await collect_stats(db, member_id)
    conditions = list(
        await db.scalars(
            select(ConditionEpisode)
            .where(ConditionEpisode.member_id == member_id)
            .order_by(ConditionEpisode.onset_date.desc().nullslast())
            .limit(15)
        )
    )
    stats["problem_list"] = [{"name": c.name, "status": c.status} for c in conditions]
    return stats


async def snapshot_health_insights(db, member_id) -> dict:
    """Whole-record review: the full history behind a Health Insights report.

    Covers family + personal history, allergies, the problem list, doctor
    visits, labs with per-test trends, the current and discontinued regimen,
    latest vitals, and vaccinations — all assembled in code. Section texts
    are truncated for prompt size; nothing here is model-generated.
    """
    member = await db.get(FamilyMember, member_id)
    today = datetime.now(UTC).date()

    conditions = list(
        await db.scalars(
            select(ConditionEpisode)
            .where(ConditionEpisode.member_id == member_id)
            .order_by(ConditionEpisode.onset_date.desc().nullslast())
            .limit(50)
        )
    )
    labs = list(
        await db.scalars(
            select(LabResult)
            .where(LabResult.member_id == member_id)
            .order_by(LabResult.record_date.desc().nullslast())
            .limit(200)
        )
    )
    visits = list(
        await db.scalars(
            select(HealthRecord)
            .where(
                HealthRecord.member_id == member_id,
                HealthRecord.is_deleted.is_(False),
                HealthRecord.record_type.in_(("doctor_visit", "discharge_summary")),
            )
            .order_by(HealthRecord.record_date.desc())
            .limit(20)
        )
    )
    active_meds = sorted(await _active_meds(db, member_id), key=lambda m: m.medicine.lower())
    past_meds = list(
        await db.scalars(
            select(Medication)
            .where(Medication.member_id == member_id, Medication.status != "active")
            .order_by(Medication.end_date.desc().nullslast())
            .limit(50)
        )
    )
    allergies = list(
        await db.scalars(
            select(Allergy)
            .where(Allergy.member_id == member_id)
            .order_by(Allergy.created_at.desc())
        )
    )
    vaccinations = list(
        await db.scalars(
            select(Vaccination)
            .where(Vaccination.member_id == member_id)
            .order_by(Vaccination.date_administered.desc())
            .limit(30)
        )
    )
    vitals = list(
        await db.scalars(
            select(VitalMeasurement)
            .where(VitalMeasurement.member_id == member_id)
            .order_by(VitalMeasurement.measured_at.desc())
            .limit(200)
        )
    )

    latest_vitals: dict[str, VitalMeasurement] = {}
    for vital in vitals:  # newest first
        latest_vitals.setdefault(vital.vital_type, vital)

    trends = _lab_trends(labs)
    flagged = [lab for lab in labs if lab.flag in ("low", "high")][:30]

    return {
        "generated_on": today.isoformat(),
        "member": {
            "name": member.name if member else "Unknown",
            "relationship": member.relationship if member else None,
            "birth_date": member.birth_date.isoformat() if member and member.birth_date else None,
            "age_years": _age_years(member.birth_date, today) if member else None,
            "sex": member.sex if member else None,
            "blood_group": member.blood_group if member else None,
            "emergency_contact": (
                f"{member.emergency_contact_name} ({member.emergency_contact_phone})"
                if member and member.emergency_contact_name
                else None
            ),
        },
        "medical_history": member.medical_history if member else None,
        "family_medical_history": member.family_medical_history if member else None,
        "allergies": [
            {
                "substance": a.substance,
                "severity": a.severity,
                "reaction": a.reaction,
                "verified": a.verified,
            }
            for a in allergies
        ],
        "conditions": [
            {
                "name": c.name,
                "icd10_code": c.icd10_code,
                "status": c.status,
                "onset_date": c.onset_date.isoformat() if c.onset_date else None,
                "resolution_date": c.resolution_date.isoformat() if c.resolution_date else None,
                "notes": c.notes,
            }
            for c in conditions
        ],
        "doctor_visits": [
            {
                "date": v.record_date.isoformat(),
                "type": v.record_type,
                "doctor_name": v.doctor_name,
                "diagnosis": v.diagnosis,
                "investigations": v.investigations,
                "summary": (v.summary or "")[:600] or None,
                "prescription": (v.prescription_text or "")[:600] or None,
            }
            for v in visits
        ],
        "labs_flagged": [{"test_name": lab.test_name, **_lab_point(lab)} for lab in flagged],
        "lab_trends": trends,
        "medications_active": [
            {
                "medicine": m.medicine,  # verbatim — never paraphrased
                "dosage": m.dosage,
                "dose_form": m.dose_form,
                "timing": m.timing,
                "schedule_type": m.schedule_type,
                "start_date": m.start_date.isoformat() if m.start_date else None,
                "prescriber": m.provider_name,
                "condition_id": str(m.condition_id) if m.condition_id else None,
            }
            for m in active_meds
        ],
        "medications_past": [
            {
                "medicine": m.medicine,
                "dosage": m.dosage,
                "start_date": m.start_date.isoformat() if m.start_date else None,
                "end_date": m.end_date.isoformat() if m.end_date else None,
                "status": m.status,
                "notes": m.notes,
            }
            for m in past_meds
        ],
        "vitals_latest": [
            {
                "vital_type": v.vital_type,
                "value_num": v.value_num,
                "value_secondary": v.value_secondary,
                "unit": v.unit,
                "glucose_context": v.glucose_context,
                "measured_at": v.measured_at.isoformat(),
            }
            for v in latest_vitals.values()
        ],
        "vaccinations": [
            {
                "name": v.name,
                "date_administered": v.date_administered.isoformat(),
                "booster_due_date": v.booster_due_date.isoformat() if v.booster_due_date else None,
            }
            for v in vaccinations
        ],
    }


async def snapshot_consolidated_report(db, member_id) -> dict:
    """Chronological ledger: every record visit + lab event, newest first."""
    member_name = await _member_name(db, member_id)
    records = list(
        await db.scalars(
            select(HealthRecord)
            .where(HealthRecord.member_id == member_id)
            .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
            .limit(50)
        )
    )
    labs = await _recent_labs(db, member_id, limit=100)
    meds = await _active_meds(db, member_id)
    return {
        "member": member_name,
        "current_medicines": [f"{m.medicine} {m.dosage or ''}".strip() for m in meds],
        "events": [
            {
                "date": str(r.record_date),
                "type": r.record_type,
                "consultant": r.doctor_name,
                "diagnoses": r.diagnosis,
                "summary": (r.summary or "")[:500],
            }
            for r in records
        ],
        "lab_events": [
            {
                "date": lab.record_date.isoformat() if lab.record_date else None,
                "test_name": lab.test_name,
                # The narrative quotes numbers, never invents them — surface
                # the numeric value alongside any string result.
                "result": lab.result if lab.result is not None else lab.value_num,
                "value_num": lab.value_num,
                "units": lab.units,
                "flag": lab.flag,
            }
            for lab in labs
        ],
    }


async def snapshot_medication_report(db, member_id) -> dict:
    """Current regimen: every active medicine with dose/timing, in code."""
    member_name = await _member_name(db, member_id)
    meds = await _active_meds(db, member_id)
    return {
        "member": member_name,
        "medications_count": len(meds),
        "medications": [
            {
                "medicine": m.medicine,  # verbatim name — never paraphrased
                "dosage": m.dosage,
                "timing": m.timing,
                "schedule_type": m.schedule_type,
                "start_date": m.start_date.isoformat() if m.start_date else None,
            }
            for m in meds
        ],
    }


async def snapshot_medication_schedule(db, member_id) -> dict:
    """Deterministic time-of-day dose schedule (computed by code, not AI)."""
    member_name = await _member_name(db, member_id)
    meds = await _active_meds(db, member_id)
    today = datetime.now(UTC).date()
    slots: dict[str, list[str]] = {
        "morning": [],
        "noon": [],
        "evening": [],
        "bedtime": [],
    }
    prn: list[str] = []
    for med in meds:
        doses = expand_day(med, today)
        label = f"{med.medicine} {med.dosage or ''}".strip()
        if not doses:
            prn.append(label)
            continue
        for dose in doses:
            slots.setdefault(dose.slot, []).append(
                label if dose.dose_count == 1 else f"{label} ({dose.annotation or dose.dose_count})"
            )
    return {
        "member": member_name,
        "date": today.isoformat(),
        "slots": {k: v for k, v in slots.items() if v},
        "as_needed": prn,
        "medications_count": len(meds),
    }


def _project_series(points: list[tuple[float, float]]) -> dict | None:
    """Least-squares projection over (day_number, value); needs >= 3 points."""
    if len(points) < 3:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    slope = linear_regression(xs, ys).slope
    return {
        "n": len(points),
        "slope_per_day": round(slope, 6),
        "projected_next": round(ys[-1] + slope, 4),
        "latest_value": ys[-1],
        "sufficient_data": True,
    }


async def snapshot_forecast(db, member_id) -> dict:
    """Statistical projections over lab/vital history — computed in code.

    The model interprets these numbers; it never recomputes a projection,
    and metrics without sufficient data carry none.
    """
    labs = await _recent_labs(db, member_id, limit=200)
    vitals = await _recent_vitals(db, member_id, days=365, limit=200)
    member_name = await _member_name(db, member_id)
    meds = await _active_meds(db, member_id)
    series: dict[str, list[tuple[float, float]]] = {}
    for lab in labs:
        if lab.value_num is not None and lab.record_date:
            key = f"lab:{lab.test_name}"
            series.setdefault(key, []).append((lab.record_date.toordinal(), lab.value_num))
    for v in vitals:
        if v.vital_type not in ("blood_pressure",):
            series.setdefault(f"vital:{v.vital_type}", []).append(
                (v.measured_at.timestamp() / 86400, v.value_num)
            )
    projections: dict[str, dict] = {}
    for key, points in series.items():
        points.sort()
        projection = _project_series(points)
        if projection:
            projections[key] = projection
    return {
        "member": member_name,
        "medications": [f"{m.medicine} {m.dosage or ''}".strip() for m in meds],
        "projections": projections,
        "note": (
            "Projections are linear extrapolations computed by code — "
            "statistical trends, NOT diagnoses."
        ),
    }


SNAPSHOT_BUILDERS = {
    "smart_report": collect_stats,
    "health_insights": snapshot_health_insights,
    "pre_consultation": snapshot_pre_consultation,
    "consultant_note": snapshot_consultant_note,
    "consolidated_report": snapshot_consolidated_report,
    "medication_report": snapshot_medication_report,
    "medication_schedule": snapshot_medication_schedule,
    "forecast": snapshot_forecast,
}

PROMPTS = {
    "smart_report": (
        "Write a smart health report for {member}. Statistics (ground truth):\n"
        "{stats}\n\nStructure: 1) Overall picture, 2) Medications, "
        "3) Flags needing attention (use the flagged labs/vitals only), "
        "4) Suggested next steps. Markdown with a `##` heading per section; "
        "short paragraphs, bullets where a list reads better."
    ),
    "health_insights": (
        "Write a comprehensive Health Insights report for {member}. Every "
        "value below was computed from the member's records and is ground "
        "truth:\n{stats}\n\n"
        "Cover these sections in order, each with a `##` heading:\n"
        "1. Executive summary — 3-4 sentences on the current state, the "
        "stability of chronic conditions, and the main focus areas.\n"
        "2. Hereditary and family history — interpret family_medical_history; "
        "if it is empty, say it is not recorded.\n"
        "3. Personal background and allergies — medical_history, "
        "vaccinations, and every allergy with severity, reaction and "
        "verification status.\n"
        "4. Problem list — one table row per condition: name, ICD-10, "
        "onset, status, clinical trajectory.\n"
        "5. Doctor visits — one table row per visit: date, doctor, "
        "diagnosis, investigations, advice. Keep each visit's date distinct.\n"
        "6. Laboratory results — a table of labs_flagged (test, result, "
        "unit, reference range, flag), then the trend for every test in "
        "lab_trends that has a previous point: both values, both dates, "
        "and the computed delta.\n"
        "7. Medications — current regimen table (name verbatim, dose, "
        "timing, start date, prescriber) and a discontinued table (dates, "
        "status, reason when recorded).\n"
        "8. Vitals — the latest reading per type with its date.\n"
        "9. Integrated assessment — connect family history, conditions, "
        "labs, vitals and medications into the risks the data supports. "
        "Frame each as a discussion point, never as a diagnosis.\n"
        "10. Next steps — questions for the next consultation and "
        "follow-ups, each tied to a flagged value or recorded condition.\n\n"
        "Use a Markdown table where a table scans better. Any section with "
        "no data must say 'not recorded in the data'. End with one line: "
        "this report is not a medical diagnosis."
    ),
    "pre_consultation": (
        "Prepare pre-consultation discussion points for {member}'s next "
        "doctor visit. Statistics (ground truth):\n{stats}\n\n"
        "Output 5-8 bullet points the patient should raise, ordered by "
        "importance. Output as a Markdown bullet list."
    ),
    "consultant_note": (
        "Write a ONE-PAGE consultant overview note for {member} — a doctor "
        "meeting this patient for the first time will spend 30 seconds on "
        "it. Snapshot (ground truth):\n{stats}\n\n"
        "Structure: Problem list (with status), Current medications (names "
        "verbatim with doses), Key flags (flagged labs/vitals only, with "
        "values), Red flags / next steps. Telegraphic lines, ≤150 words. "
        "Markdown: a `##` heading per section, bullets under each."
    ),
    "consolidated_report": (
        "Compile a consolidated medical report for {member}: the recorded "
        "history as one chronological ledger, newest first. Event ledger "
        "(ground truth):\n{stats}\n\n"
        "One block per event using its date/type/consultant/diagnoses as "
        "given — never merge two dates, never invent a visit or value. "
        "Markdown: one `###` heading per event (date + type), brief "
        "paragraph beneath."
    ),
    "medication_report": (
        "Write a comprehensive medication report for {member}. Regimen "
        "(ground truth, computed from the medication records):\n{stats}\n\n"
        "Cover: regimen overview (how many medicines, overall complexity), "
        "one entry per medicine (name verbatim, dose, timing), practical "
        "notes for the patient, and what to discuss with the prescriber. "
        "Never invent an interaction or an indication not implied by the "
        "data. Markdown: `##` headings per section, one bullet per medicine."
    ),
    "medication_schedule": (
        "Render the daily medicine schedule for {member} as a printable "
        "poster text. The slot grouping was computed by code — reproduce it "
        "exactly:\n{stats}\n\n"
        "Format: one `##` heading per slot (morning/noon/evening/bedtime) "
        "with its medicines as bullets, then an 'As needed' section. Do not "
        "add, drop, or re-time any medicine."
    ),
    "forecast": (
        "Write a predictive analytics narrative for {member}. The "
        "PROJECTIONS below were computed by linear regression over the "
        "member's real history — they are ground truth: quote them "
        "verbatim, never recompute or invent a projection, and state that "
        "each is a statistical trend, not a diagnosis.\n{stats}\n\n"
        "For each projected metric: the trend (direction, magnitude), what "
        "to watch, and questions to ask the doctor. Metrics absent from "
        "the projections have insufficient data — write so. Markdown: a "
        "`##` heading per metric."
    ),
}


async def build_snapshot(db: AsyncSession, member_id: uuid.UUID, kind: str) -> dict:
    if kind not in SNAPSHOT_BUILDERS:
        raise ValueError(f"Unknown report kind: {kind}")
    return await SNAPSHOT_BUILDERS[kind](db, member_id)


async def report_stream(
    db: AsyncSession,
    member_id: uuid.UUID,
    kind: str,
    provider,
    verifier,
) -> AsyncIterator[dict]:
    """Snapshot (code) → one narrative call (model) → persist + audit."""
    from app.services.ai.verification import schedule_audit

    yield {"stage": "stats", "message": "collecting member statistics"}
    stats = await build_snapshot(db, member_id, kind)

    prompt = PROMPTS[kind].format(
        member=stats.get("member", "Unknown"),
        stats=json.dumps(stats, ensure_ascii=False, indent=1, default=str),
    )
    yield {"stage": "narrating", "message": "AI writing report"}
    collected: list[str] = []
    stream_fn = getattr(provider, "stream", None)
    if stream_fn is not None:
        deltas = await stream_fn(prompt, system=REPORT_SYSTEM)
        async for delta in deltas:
            collected.append(delta)
            yield {"stage": "narrating", "delta": delta}
    else:
        text = await provider.complete(prompt, system=REPORT_SYSTEM)
        collected.append(text)
        yield {"stage": "narrating", "delta": text}
    content = "".join(collected)

    verification_id = None
    if verifier:
        yield {"stage": "verifying", "message": "auditing claims"}
        verification_id = await schedule_audit(
            db,
            member_id,
            f"report:{kind}",
            content,
            verifier,
            kind=kind,
            commit=False,
        )

    insight = Insight(
        member_id=member_id,
        kind=kind,
        content=content,
        sources_json=json.dumps(
            {k: v for k, v in stats.items() if k != "member"},
            ensure_ascii=False,
            default=str,
        ),
        verification_id=verification_id,
        provider_used=getattr(provider, "name", "unknown"),
    )
    db.add(insight)
    await db.commit()

    yield {
        "stage": "complete",
        "report": {
            "id": str(insight.id),
            "kind": kind,
            "content": content,
            "provider_used": insight.provider_used,
            "sources": (json.loads(insight.sources_json) if insight.sources_json else None),
            "verification_id": str(verification_id) if verification_id else None,
            "created_at": insight.created_at.isoformat(),
        },
    }


async def latest_report(db: AsyncSession, member_id: uuid.UUID, kind: str) -> Insight | None:
    return await db.scalar(
        select(Insight)
        .where(Insight.member_id == member_id, Insight.kind == kind)
        .order_by(Insight.created_at.desc())
        .limit(1)
    )
