"""Shared helper for building Medication rows from API payloads.

Used by the medications router and by member creation, which seeds the
"currently taking" list from the add-member form.
"""

import uuid

from app.models.medication import Medication, normalize_medicine_key
from app.schemas.medication import MedicationCreate


def new_medication(member_id: uuid.UUID, payload: MedicationCreate) -> Medication:
    """Unpersisted Medication from a create payload; validates the schedule."""
    return Medication(
        member_id=member_id,
        record_id=payload.record_id,
        medicine=payload.medicine,
        medicine_key=normalize_medicine_key(payload.medicine),
        dose_form=payload.dose_form,
        dosage=payload.dosage,
        timing=payload.timing,
        duration_days=payload.duration_days,
        start_date=payload.start_date,
        schedule_type=payload.schedule_type,
        schedule_json=payload.schedule_payload(),
        provider_name=payload.provider_name,
        notes=payload.notes,
    )
