"""Condition episode schemas."""

import uuid
from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.models.condition import ConditionStatus
from app.schemas._datetime import UTCDateTime


class ConditionCreate(BaseModel):
    """Condition episode creation request."""

    name: str = Field(min_length=1, max_length=200)
    icd10_code: str | None = Field(
        default=None, min_length=3, max_length=10, description="ICD-10 code (e.g. E11.9)"
    )
    status: ConditionStatus = ConditionStatus.ACTIVE
    onset_date: date | None = None
    resolution_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _check_dates(self) -> "ConditionCreate":
        if self.resolution_date and self.onset_date and self.resolution_date < self.onset_date:
            raise ValueError("resolution_date cannot precede onset_date")
        if self.status == ConditionStatus.RESOLVED and not self.resolution_date:
            raise ValueError("resolved conditions require a resolution_date")
        return self


class ConditionUpdate(BaseModel):
    """Condition episode update request (partial)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    icd10_code: str | None = Field(default=None, min_length=3, max_length=10)
    status: ConditionStatus | None = None
    onset_date: date | None = None
    resolution_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ConditionResponse(BaseModel):
    """Condition episode response with linked-entity counts."""

    id: uuid.UUID
    member_id: uuid.UUID
    name: str
    icd10_code: str | None
    status: ConditionStatus
    onset_date: date | None
    resolution_date: date | None
    notes: str | None
    created_at: UTCDateTime
    record_count: int = 0
    medication_count: int = 0

    model_config = {"from_attributes": True}
