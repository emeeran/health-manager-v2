import uuid
from datetime import date, time
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.record import RecordType
from app.schemas._datetime import UTCDateTime

# household | caregiver | private — role ceiling enforced at read time:
# private → admins only, caregiver → admins + members, household → all.
ConfidentialityLevel = Literal["household", "caregiver", "private"]


class RecordCreate(BaseModel):
    record_type: RecordType = RecordType.OTHER
    record_date: date
    record_time: time | None = None
    clinical_data: dict[str, Any] | None = None
    diagnosis: str | None = Field(default=None, max_length=5000)
    investigations: str | None = Field(default=None, max_length=5000)
    prescription_text: str | None = Field(default=None, max_length=10000)
    summary: str | None = Field(default=None, max_length=10000)
    doctor_name: str | None = Field(default=None, max_length=200)
    provider_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    confidentiality_level: ConfidentialityLevel = "household"


class RecordUpdate(BaseModel):
    record_type: RecordType | None = None
    record_date: date | None = None
    record_time: time | None = None
    clinical_data: dict[str, Any] | None = None
    diagnosis: str | None = Field(default=None, max_length=5000)
    investigations: str | None = Field(default=None, max_length=5000)
    prescription_text: str | None = Field(default=None, max_length=10000)
    summary: str | None = Field(default=None, max_length=10000)
    doctor_name: str | None = Field(default=None, max_length=200)
    provider_id: uuid.UUID | None = None
    tags: list[str] | None = None
    confidentiality_level: ConfidentialityLevel | None = None


class RecordMergeRequest(BaseModel):
    """Merge the URL record (the duplicate) into ``duplicate_of_id``."""

    duplicate_of_id: uuid.UUID


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    file_path: str
    content_hash: str
    file_size: int
    mime: str
    original_name: str
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class RecordResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    record_type: str
    record_date: date
    record_time: time | None
    clinical_data: dict[str, Any] | None
    diagnosis: str | None
    investigations: str | None = None
    prescription_text: str | None
    summary: str | None
    doctor_name: str | None
    provider_id: uuid.UUID | None = None
    provider_name: str | None = None
    tags: list[str]
    is_deleted: bool
    confidentiality_level: str = "household"
    # Plaintext SHA-256 of the clinical payload (dedup/merge, Phase 10)…
    content_hash: str | None = None
    # …and set when this record was merged away into another one.
    merged_into_id: uuid.UUID | None = None
    created_at: UTCDateTime
    attachments: list[AttachmentResponse]

    model_config = {"from_attributes": True}


class ApplyExtraction(BaseModel):
    """Persist an AI extraction result onto a record.

    Field semantics mirror the frontend's former PATCH-based apply: absent
    optional fields keep the record's current values; clinical_data replaces
    the stored payload; labs and vitals inside it become linked domain rows.
    """

    clinical_data: dict[str, Any]
    summary: str | None = Field(default=None, max_length=10000)
    diagnosis: str | None = Field(default=None, max_length=5000)
    record_date: date | None = None
    doctor_name: str | None = Field(default=None, max_length=200)
