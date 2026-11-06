"""Allergy schemas."""

import uuid

from pydantic import BaseModel, Field
from app.schemas._datetime import UTCDateTime


class AllergyCreate(BaseModel):
    """Allergy creation request."""

    substance: str = Field(min_length=1, max_length=255, description="Allergen substance")
    severity: str = Field(
        default="mild", pattern="^(mild|moderate|severe)$", description="Reaction severity"
    )
    reaction: str | None = Field(default=None, max_length=500, description="Observed reaction")
    verified: bool = Field(default=False, description="Confirmed by a clinician")


class AllergyUpdate(BaseModel):
    """Allergy update request."""

    substance: str | None = Field(default=None, min_length=1, max_length=255)
    severity: str | None = Field(default=None, pattern="^(mild|moderate|severe)$")
    reaction: str | None = Field(default=None, max_length=500)
    verified: bool | None = None


class AllergyResponse(BaseModel):
    """Allergy response."""

    id: uuid.UUID
    member_id: uuid.UUID
    substance: str
    severity: str
    reaction: str | None
    verified: bool
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class AllergyConflict(BaseModel):
    """A potential allergen–medication conflict (decision-support hint)."""

    allergy: str = Field(description="Allergy substance")
    severity: str = Field(description="Allergy severity")
    medication: str = Field(description="Medication display name")
    matched_on: str = Field(description='"medicine_name"')
