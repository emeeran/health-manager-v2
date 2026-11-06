import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.base import Relationship
from app.schemas._datetime import UTCDateTime


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: Relationship = Relationship.SELF
    birth_date: date | None = None
    # male | female | other — selects the CDC growth-table series.
    sex: str | None = Field(default=None, pattern="^(male|female|other)$")
    cloud_ai_consent: bool = True
    web_factcheck_consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)
    medical_history: str | None = Field(default=None, max_length=5000)
    family_medical_history: str | None = Field(default=None, max_length=5000)
    blood_group: str | None = Field(default=None, max_length=8)
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    relationship: Relationship | None = None
    birth_date: date | None = None
    sex: str | None = Field(default=None, pattern="^(male|female|other)$")
    cloud_ai_consent: bool | None = None
    web_factcheck_consent: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)
    medical_history: str | None = Field(default=None, max_length=5000)
    family_medical_history: str | None = Field(default=None, max_length=5000)
    current_medications: str | None = Field(default=None, max_length=5000)
    blood_group: str | None = Field(default=None, max_length=8)
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)


class MedicationMergeSuggestion(BaseModel):
    """AI-merged current-medications text — the client decides to keep it."""

    suggestion: str


class MemberResponse(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID
    name: str
    relationship: str
    birth_date: date | None
    sex: str | None = None
    cloud_ai_consent: bool
    web_factcheck_consent: bool
    notes: str | None
    phone: str | None = None
    address: str | None = None
    medical_history: str | None = None
    family_medical_history: str | None = None
    current_medications: str | None = None
    blood_group: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
