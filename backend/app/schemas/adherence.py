"""Read-only views of today's dose schedule (pill tracking removed)."""

import uuid
from datetime import date

from pydantic import BaseModel
from app.schemas._datetime import UTCDateTime


class DoseView(BaseModel):
    medication_id: uuid.UUID
    medicine: str
    dosage: str | None
    slot: str
    dose_count: int
    scheduled_time: UTCDateTime
    annotation: str | None


class PrnView(BaseModel):
    medication_id: uuid.UUID
    medicine: str
    dosage: str | None


class AdherenceTodayResponse(BaseModel):
    date: date
    doses: list[DoseView]
    prn: list[PrnView]
