"""Prescription ↔ doctor-visit integration.

A prescription filed within ``VISIT_LINK_DAYS`` of a doctor-visit record
for the same member belongs to that visit: when the prescription is
missing a doctor, provider, or diagnosis, the linked visit's values are
auto-filled so the two records read as one consultation. Prescriptions
with no nearby visit stay standalone — no linking is forced.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HealthRecord

VISIT_LINK_DAYS = 7


async def find_linked_visit(
    db: AsyncSession, member_id: uuid.UUID, record_date: date | None
) -> HealthRecord | None:
    """Nearest doctor visit for this member within ±VISIT_LINK_DAYS, or None."""
    if record_date is None:
        return None
    window_start = record_date - timedelta(days=VISIT_LINK_DAYS)
    window_end = record_date + timedelta(days=VISIT_LINK_DAYS)
    candidates = list(
        await db.scalars(
            select(HealthRecord).where(
                HealthRecord.member_id == member_id,
                HealthRecord.record_type == "doctor_visit",
                HealthRecord.is_deleted.is_(False),
                HealthRecord.record_date.between(window_start, window_end),
            )
        )
    )
    if not candidates:
        return None
    return min(candidates, key=lambda r: abs((r.record_date - record_date).days))


def apply_visit_autofill(record: HealthRecord, visit: HealthRecord) -> list[str]:
    """Fill the prescription's empty visit-ish fields from the visit.

    Returns the names of the fields that were filled (for logging/tests).
    Existing values are never overwritten.
    """
    filled: list[str] = []
    if not record.doctor_name and visit.doctor_name:
        record.doctor_name = visit.doctor_name
        filled.append("doctor_name")
    if not record.provider_id and visit.provider_id:
        record.provider_id = visit.provider_id
        filled.append("provider_id")
    if not record.diagnosis and visit.diagnosis:
        record.diagnosis = visit.diagnosis
        filled.append("diagnosis")
    return filled
