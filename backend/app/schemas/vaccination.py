"""Vaccination schemas."""

import uuid
from datetime import date

from pydantic import BaseModel, Field
from app.schemas._datetime import UTCDateTime


class VaccinationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    date_administered: date
    booster_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class VaccinationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    date_administered: date | None = None
    booster_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class VaccinationResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    name: str
    date_administered: date
    booster_due_date: date | None
    notes: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
