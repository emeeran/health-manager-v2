"""Dashboard service — aggregates the household overview.

Ported from v1's dashboard_service + health_score_service (core slice:
health scores, alerts, activity, family strip). Adaptations to v2's
domain model are noted inline; v1's preventive-care and vaccination
sections are omitted because v2 has no PreventiveCareService or
Vaccination model yet. Every number here is computed from the DB in
code — no model inference involved.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    ConditionEpisode,
    Conversation,
    FamilyMember,
    HealthRecord,
    Household,
    LabResult,
    Medication,
    Notification,
    Provider,
    Reminder,
    Vaccination,
    VitalMeasurement,
    VitalType,
)

logger = logging.getLogger(__name__)

RECENT_LAB_DAYS = 90


def _risk_level(score: int) -> str:
    if score < 40:
        return "high"
    if score <= 65:
        return "moderate"
    return "low"


def compute_health_score(
    *,
    bmi: float | None,
    conditions_count: int,
    recent_visit: bool,
    lab_normal: int,
    lab_abnormal: int,
    active_meds: int,
    profile_points: int,
    days_since_record: int | None,
) -> tuple[int, dict]:
    """v1's category breakdown, adapted to v2 data sources.

    BMI comes from vital_measurements (v2 members carry no height/weight),
    conditions from condition_episodes, labs from lab_results.flag
    (medication_tracking in v1 folded in adherence from adherence_logs;
    pill tracking has been removed).
    """
    breakdown: dict[str, dict] = {}
    total = 0

    # 1. BMI (0-20) — from the latest height + weight vitals.
    bmi_score, bmi_label = 10, "No BMI data available"
    if bmi is not None:
        if 18.5 <= bmi < 25:
            bmi_score, bmi_label = 20, f"BMI {bmi} — normal range"
        elif 25 <= bmi < 30:
            bmi_score, bmi_label = 14, f"BMI {bmi} — overweight"
        elif 30 <= bmi < 35:
            bmi_score, bmi_label = 8, f"BMI {bmi} — obese class I"
        else:
            bmi_score, bmi_label = 5, f"BMI {bmi} — obese class II+"
    total += bmi_score
    breakdown["bmi"] = {"score": bmi_score, "max": 20, "label": bmi_label}

    # 2. Conditions management (0-20).
    if conditions_count == 0:
        cond_score, cond_label = 20, "No known chronic conditions"
    elif recent_visit:
        cond_score, cond_label = (
            16,
            (f"{conditions_count} condition(s), recent checkup within 6 months"),
        )
    else:
        cond_score, cond_label = 8, (f"{conditions_count} condition(s), no recent checkup")
    total += cond_score
    breakdown["conditions_management"] = {
        "score": cond_score,
        "max": 20,
        "label": cond_label,
    }

    # 3. Lab compliance (0-20) — flag columns, no text parsing.
    if lab_normal == 0 and lab_abnormal == 0:
        lab_score, lab_label = 10, "No recent lab data"
    elif lab_abnormal == 0:
        lab_score, lab_label = 20, "All recent lab results normal"
    elif lab_normal >= lab_abnormal:
        lab_score, lab_label = 14, (f"Mostly normal ({lab_normal} normal, {lab_abnormal} flagged)")
    else:
        lab_score, lab_label = 6, f"{lab_abnormal} abnormal result(s) flagged"
    total += lab_score
    breakdown["lab_compliance"] = {"score": lab_score, "max": 20, "label": lab_label}

    # 4. Medication tracking (0-15).
    if active_meds == 0:
        med_score, med_label = 15, "No active medications"
    else:
        med_score, med_label = 12, f"{active_meds} medication(s) actively tracked"
    total += med_score
    breakdown["medication_tracking"] = {"score": med_score, "max": 15, "label": med_label}

    # 5. Profile completeness (0-15) — blood group / ICE contact / history.
    profile_score = profile_points
    total += profile_score
    breakdown["profile_completeness"] = {
        "score": profile_score,
        "max": 15,
        "label": "Complete" if profile_score >= 15 else "Missing member profile data",
    }

    # 6. Record recency (0-10).
    if days_since_record is None:
        recency_score, recency_label = 0, "No records yet"
    elif days_since_record <= 30:
        recency_score, recency_label = 10, f"Last record {days_since_record} days ago"
    elif days_since_record <= 90:
        recency_score, recency_label = 7, f"Last record {days_since_record} days ago"
    elif days_since_record <= 180:
        recency_score, recency_label = 4, (f"Last record {days_since_record // 30} months ago")
    else:
        recency_score, recency_label = 1, (f"Last record over {days_since_record // 30} months ago")
    total += recency_score
    breakdown["record_recency"] = {"score": recency_score, "max": 10, "label": recency_label}

    return min(100, total), breakdown


class DashboardService:
    """Aggregate household-level dashboard data (core slice)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_household_summary(self, household_id: uuid.UUID) -> dict:
        today = date.today()
        since_30 = today - timedelta(days=30)

        members = list(
            await self.db.scalars(
                select(FamilyMember)
                .where(FamilyMember.household_id == household_id)
                .order_by(FamilyMember.created_at)
            )
        )
        member_ids = [m.id for m in members]
        name_of = {m.id: m.name for m in members}

        if not members:
            return {
                "alerts": [],
                "vaccination_status": {
                    "total_vaccinations": 0,
                    "overdue_count": 0,
                },
                "medication_summary": {
                    "total_active_medications": 0,
                    "members_with_medications": 0,
                    "refill_reminders": [],
                },
                "scores": [],
                "record_activity": {"total_last_30_days": 0, "by_type": {}},
                "activity_feed": [],
                "risk_summary": {
                    "high_risk_members": 0,
                    "moderate_risk_members": 0,
                    "low_risk_members": 0,
                },
                "members": [],
                "household_name": await self._household_name(household_id),
                "providers_count": 0,
                "unread_notifications": 0,
                "upcoming_reminders": [],
                "recent_records": [],
                "conversations_count": 0,
            }

        # --- Batch reads (one shared AsyncSession — sequential by design) ---
        records = list(
            await self.db.scalars(
                select(HealthRecord)
                .where(
                    HealthRecord.member_id.in_(member_ids),
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.record_date.desc())
                .limit(len(member_ids) * 20 + 30)
            )
        )
        meds = list(
            await self.db.scalars(select(Medication).where(Medication.member_id.in_(member_ids)))
        )
        labs = list(
            await self.db.scalars(select(LabResult).where(LabResult.member_id.in_(member_ids)))
        )
        vitals = list(
            await self.db.scalars(
                select(VitalMeasurement)
                .where(VitalMeasurement.member_id.in_(member_ids))
                .order_by(VitalMeasurement.measured_at.desc())
            )
        )
        conditions = list(
            await self.db.scalars(
                select(ConditionEpisode).where(
                    ConditionEpisode.member_id.in_(member_ids),
                    ConditionEpisode.status != "resolved",
                )
            )
        )
        allergies = list(
            await self.db.scalars(select(Allergy).where(Allergy.member_id.in_(member_ids)))
        )
        vaccinations = list(
            await self.db.scalars(select(Vaccination).where(Vaccination.member_id.in_(member_ids)))
        )
        overdue_boosters = [
            v for v in vaccinations if v.booster_due_date is not None and v.booster_due_date < today
        ]

        alerts = await self._alerts(
            household_id,
            members,
            today,
            labs=labs,
            meds=meds,
            allergies=allergies,
            overdue_boosters=overdue_boosters,
        )

        # --- Per-member health scores ---
        scores = []
        for m in members:
            score, breakdown = self._member_score(
                m,
                today,
                records=records,
                meds=meds,
                labs=labs,
                vitals=vitals,
                conditions=conditions,
            )
            scores.append(
                {
                    "member_id": str(m.id),
                    "name": m.name,
                    "health_score": score,
                    "risk_level": _risk_level(score),
                    "score_breakdown": breakdown,
                }
            )

        # --- Record activity (last 30 days) ---
        by_type: dict[str, int] = {}
        for r in records:
            if r.record_date is not None and r.record_date >= since_30:
                by_type[str(r.record_type)] = by_type.get(str(r.record_type), 0) + 1

        # --- Activity feed: records + labs + vitals, newest first ---
        feed: list[dict] = []
        for r in records[:40]:
            feed.append(
                {
                    "id": str(r.id),
                    "kind": "record",
                    "member_id": str(r.member_id),
                    "member_name": name_of.get(r.member_id, "—"),
                    "title": r.diagnosis or str(r.record_type),
                    "occurred_at": r.record_date.isoformat() if r.record_date else None,
                }
            )
        for lab in labs:
            feed.append(
                {
                    "id": str(lab.id),
                    "kind": "lab",
                    "member_id": str(lab.member_id),
                    "member_name": name_of.get(lab.member_id, "—"),
                    "title": f"{lab.test_name} = {lab.result or lab.value_num or '?'}"
                    + (f" ({lab.flag})" if lab.flag else ""),
                    "occurred_at": lab.record_date.isoformat() if lab.record_date else None,
                }
            )
        for v in vitals[:40]:
            feed.append(
                {
                    "id": str(v.id),
                    "kind": "vital",
                    "member_id": str(v.member_id),
                    "member_name": name_of.get(v.member_id, "—"),
                    "title": f"{v.vital_type} = {v.value_num}"
                    + (f"/{v.value_secondary}" if v.value_secondary else ""),
                    "occurred_at": v.measured_at.date().isoformat() if v.measured_at else None,
                }
            )
        feed.sort(key=lambda item: item["occurred_at"] or "", reverse=True)
        activity_feed = feed[:30]

        # --- Medication summary ---
        active_meds = [m for m in meds if m.status == "active"]
        refill_window = today + timedelta(days=5)
        refill_reminders = [
            {
                "member_id": str(m.member_id),
                "member_name": name_of.get(m.member_id, "—"),
                "medicine": m.medicine,
                "dosage": m.dosage,
                "end_date": m.end_date.isoformat() if m.end_date else None,
            }
            for m in active_meds
            if m.end_date is not None and m.end_date <= refill_window
        ][:5]

        # --- Scalars / household chrome ---
        providers_count = (
            await self.db.scalar(
                select(func.count())
                .select_from(Provider)
                .where(Provider.household_id == household_id)
            )
            or 0
        )
        unread_notifications = (
            await self.db.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.household_id == household_id,
                    Notification.read_at.is_(None),
                )
            )
            or 0
        )
        conversations_count = (
            await self.db.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.household_id == household_id)
            )
            or 0
        )
        reminders = list(
            await self.db.scalars(
                select(Reminder)
                .where(
                    Reminder.member_id.in_(member_ids),
                    Reminder.done.is_(False),
                    Reminder.remind_at >= datetime.now(UTC).replace(tzinfo=None),
                )
                .order_by(Reminder.remind_at.asc())
                .limit(5)
            )
        )
        recent_records = [
            {
                "id": str(r.id),
                "member_id": str(r.member_id),
                "member_name": name_of.get(r.member_id, "—"),
                "record_type": str(r.record_type),
                "record_date": r.record_date.isoformat() if r.record_date else None,
                "diagnosis": r.diagnosis,
                "summary": (r.summary or "")[:120] or None,
            }
            for r in records[:30]
        ]

        return {
            "alerts": alerts,
            "vaccination_status": {
                "total_vaccinations": len(vaccinations),
                "overdue_count": len(overdue_boosters),
            },
            "medication_summary": {
                "total_active_medications": len(active_meds),
                "members_with_medications": len({m.member_id for m in active_meds}),
                "refill_reminders": refill_reminders,
            },
            "scores": scores,
            "record_activity": {
                "total_last_30_days": sum(by_type.values()),
                "by_type": by_type,
            },
            "activity_feed": activity_feed,
            "risk_summary": {
                "high_risk_members": sum(1 for s in scores if s["risk_level"] == "high"),
                "moderate_risk_members": sum(1 for s in scores if s["risk_level"] == "moderate"),
                "low_risk_members": sum(1 for s in scores if s["risk_level"] == "low"),
            },
            "members": [
                {
                    "id": str(m.id),
                    "name": m.name,
                    "relationship": m.relationship,
                    "birth_date": m.birth_date.isoformat() if m.birth_date else None,
                    "blood_group": m.blood_group,
                    "health_score": next(
                        (s["health_score"] for s in scores if s["member_id"] == str(m.id)),
                        None,
                    ),
                }
                for m in members
            ],
            "household_name": await self._household_name(household_id),
            "providers_count": providers_count,
            "unread_notifications": unread_notifications,
            "upcoming_reminders": [
                {
                    "id": str(r.id),
                    "title": r.title,
                    # Stored naive-UTC — mark the Z so the browser parses UTC, not local.
                    "remind_at": (r.remind_at.isoformat() + "Z") if r.remind_at else None,
                    "repeat": r.repeat,
                }
                for r in reminders
            ],
            "recent_records": recent_records,
            "conversations_count": conversations_count,
        }

    # ── pieces ────────────────────────────────────────────────────────

    async def _household_name(self, household_id: uuid.UUID) -> str:
        household = await self.db.get(Household, household_id)
        return household.name if household else "My Family"

    def _member_score(
        self,
        member: FamilyMember,
        today: date,
        *,
        records: list[HealthRecord],
        meds: list[Medication],
        labs: list[LabResult],
        vitals: list[VitalMeasurement],
        conditions: list[ConditionEpisode],
    ) -> tuple[int, dict]:
        my_records = [r for r in records if r.member_id == member.id]
        my_labs = [
            lab
            for lab in labs
            if lab.member_id == member.id
            and lab.record_date is not None
            and lab.record_date >= today - timedelta(days=RECENT_LAB_DAYS)
        ]
        lab_normal = sum(1 for lab in my_labs if lab.flag == "normal" or lab.flag is None)
        lab_abnormal = sum(1 for lab in my_labs if lab.flag in ("low", "high"))
        my_meds = [m for m in meds if m.member_id == member.id and m.status == "active"]
        my_conditions = [c for c in conditions if c.member_id == member.id]
        recent_visit = any(
            r.record_type == "doctor_visit" and r.record_date >= today - timedelta(days=182)
            for r in my_records
        )

        # BMI from latest height + weight vitals.
        height = weight = None
        for v in vitals:
            if v.member_id != member.id:
                continue
            if height is None and v.vital_type == VitalType.HEIGHT.value:
                height = v.value_num  # cm expected
            if weight is None and v.vital_type == VitalType.WEIGHT.value:
                weight = v.value_num  # kg expected
        bmi = None
        if height and weight and height > 0:
            bmi = round(weight / (height / 100) ** 2, 1)

        profile_points = 0
        if member.blood_group:
            profile_points += 5
        if member.emergency_contact_name or member.emergency_contact_phone:
            profile_points += 5
        if member.medical_history:
            profile_points += 5

        days_since = None
        if my_records:
            latest = max(r.record_date for r in my_records if r.record_date)
            if latest:
                days_since = (today - latest).days

        return compute_health_score(
            bmi=bmi,
            conditions_count=len(my_conditions),
            recent_visit=recent_visit,
            lab_normal=lab_normal,
            lab_abnormal=lab_abnormal,
            active_meds=len(my_meds),
            profile_points=profile_points,
            days_since_record=days_since,
        )

    async def _alerts(
        self,
        household_id: uuid.UUID,
        members: list[FamilyMember],
        today: date,
        *,
        labs: list[LabResult],
        meds: list[Medication],
        allergies: list[Allergy],
        overdue_boosters: list[Vaccination],
    ) -> list[dict]:
        """Deterministic alerts: overdue boosters, abnormal labs,
        allergy-med conflicts."""
        name_of = {m.id: m.name for m in members}
        alerts: list[dict] = []

        # Overdue boosters.
        for vacc in overdue_boosters:
            due = vacc.booster_due_date
            if due is None:  # the caller filters these; guard for the type
                continue
            alerts.append(
                {
                    "id": f"booster-{vacc.id}",
                    "member_id": str(vacc.member_id),
                    "member_name": name_of.get(vacc.member_id, "—"),
                    "alert_type": "overdue_booster",
                    "severity": "medium",
                    "title": f"{vacc.name} booster overdue",
                    "message": (f"Booster for {vacc.name} was due {due.isoformat()}"),
                    "test_name": None,
                    "value": due.isoformat(),
                    "reference": None,
                }
            )

        # Abnormal labs in the recent window.
        for lab in labs:
            if lab.flag not in ("low", "high"):
                continue
            # Labs without a recorded date are treated as recent.
            if lab.record_date is not None and lab.record_date < today - timedelta(
                days=RECENT_LAB_DAYS
            ):
                continue
            severity = "medium"
            if (
                lab.value_num is not None
                and lab.ref_high_num
                and lab.value_num >= 1.5 * lab.ref_high_num
            ):
                severity = "high"
            elif (
                lab.value_num is not None
                and lab.ref_low_num
                and lab.value_num <= 0.5 * lab.ref_low_num
            ):
                severity = "high"
            alerts.append(
                {
                    "id": str(lab.id),
                    "member_id": str(lab.member_id),
                    "member_name": name_of.get(lab.member_id, "—"),
                    "alert_type": "abnormal_lab",
                    "severity": severity,
                    "title": f"{lab.test_name} {lab.flag}",
                    "message": (
                        f"{lab.test_name} = {lab.result or lab.value_num or '?'} "
                        f"{lab.units or ''} flagged {lab.flag}".strip()
                    ),
                    "test_name": lab.test_name,
                    "value": str(lab.result or lab.value_num or ""),
                    "reference": lab.ref_value,
                }
            )

        # Active allergy × active-medication conflicts (simple name match).
        active_meds = [m for m in meds if m.status == "active"]
        for allergy in allergies:
            tokens = {"".join(ch for ch in allergy.substance.lower() if ch.isalnum())}
            for med in active_meds:
                med_key = "".join(ch for ch in med.medicine.lower() if ch.isalnum())
                if any(t and t in med_key for t in tokens):
                    alerts.append(
                        {
                            "id": f"allergy-{allergy.id}-{med.id}",
                            "member_id": str(allergy.member_id),
                            "member_name": name_of.get(allergy.member_id, "—"),
                            "alert_type": "allergy_conflict",
                            "severity": "high",
                            "title": "Allergy conflict",
                            "message": (
                                f"{name_of.get(allergy.member_id, 'This member')} is "
                                f"allergic to {allergy.substance} but has active "
                                f"medication {med.medicine}"
                            ),
                            "test_name": None,
                            "value": med.medicine,
                            "reference": allergy.substance,
                        }
                    )

        return alerts[:10]
