"""Symptom journal schemas."""

import uuid
from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.models.symptom import SymptomSeverity
from app.schemas._datetime import UTCDateTime

# Preset symptom keys the frontend quick-tap offers; free text is also
# accepted and stored verbatim (normalized).
PRESET_SYMPTOMS: tuple[str, ...] = (
    "headache",
    "nausea",
    "dizziness",
    "fatigue",
    "abdominal_pain",
    "chest_pain",
    "shortness_of_breath",
    "joint_pain",
    "back_pain",
    "rash",
    "fever",
    "cough",
    "insomnia",
    "anxiety",
    "swelling",
    "numbness",
    "palpitations",
    "constipation",
    "diarrhea",
    "vomiting",
)


class SymptomCreate(BaseModel):
    symptom: str = Field(min_length=1, max_length=100)
    severity: SymptomSeverity = SymptomSeverity.MODERATE
    started_at: date
    resolved_at: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _resolution_after_onset(self) -> "SymptomCreate":
        if self.resolved_at and self.resolved_at < self.started_at:
            raise ValueError("resolved_at cannot precede started_at")
        return self


class SymptomUpdate(BaseModel):
    symptom: str | None = Field(default=None, min_length=1, max_length=100)
    severity: SymptomSeverity | None = None
    started_at: date | None = None
    resolved_at: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SymptomResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    symptom: str
    severity: SymptomSeverity
    started_at: date
    resolved_at: date | None
    notes: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
