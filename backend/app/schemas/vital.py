import uuid

from pydantic import BaseModel, Field

from app.models.vital import GlucoseContext, VitalType
from app.schemas._datetime import UTCDateTime


class VitalCreate(BaseModel):
    vital_type: VitalType
    # NaN/Inf would silently corrupt trends and growth z-scores (SQLite
    # stores NaN as NULL, Inf as a huge float).
    value_num: float = Field(allow_inf_nan=False)
    value_secondary: float | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = Field(default=None, max_length=20)
    glucose_context: GlucoseContext | None = None
    measured_at: UTCDateTime
    source: str | None = Field(default=None, max_length=50)


class VitalResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    record_id: uuid.UUID | None
    vital_type: str
    value_num: float
    value_secondary: float | None
    unit: str | None
    glucose_context: str | None
    measured_at: UTCDateTime
    source: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
