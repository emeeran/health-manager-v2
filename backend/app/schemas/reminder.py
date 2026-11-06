import uuid

from pydantic import BaseModel, Field
from app.schemas._datetime import UTCDateTime


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    member_id: uuid.UUID | None = None
    remind_at: UTCDateTime
    repeat: str = Field(default="none", pattern="^(none|daily|weekly|monthly)$")
    notes: str | None = Field(default=None, max_length=2000)


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    remind_at: UTCDateTime | None = None
    repeat: str | None = Field(default=None, pattern="^(none|daily|weekly|monthly)$")
    done: bool | None = None


class ReminderResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID | None
    title: str
    notes: str | None
    remind_at: UTCDateTime
    repeat: str
    done: bool
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
