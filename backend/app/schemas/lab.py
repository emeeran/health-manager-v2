import uuid
from datetime import date

from pydantic import BaseModel, Field
from app.schemas._datetime import UTCDateTime


class LabCreate(BaseModel):
    test_name: str = Field(min_length=1, max_length=200)
    result: str | None = Field(default=None, max_length=200)
    units: str | None = Field(default=None, max_length=50)
    ref_value: str | None = Field(default=None, max_length=200)
    value_num: float | None = Field(default=None, allow_inf_nan=False)
    ref_low_num: float | None = Field(default=None, allow_inf_nan=False)
    ref_high_num: float | None = Field(default=None, allow_inf_nan=False)
    flag: str | None = Field(default=None, pattern="^(low|normal|high)$")
    record_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class LabResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    record_id: uuid.UUID | None
    test_name: str
    result: str | None
    units: str | None
    ref_value: str | None
    note: str | None
    value_num: float | None
    ref_low_num: float | None
    ref_high_num: float | None
    flag: str | None
    record_date: date | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
