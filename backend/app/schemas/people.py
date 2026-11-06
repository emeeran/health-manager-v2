"""Schemas for phase 9 people breadth: providers, assignments, insurance,
emergency card, history feed."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.insurance import ClaimStatus
from app.schemas._datetime import UTCDateTime


# ── Providers ─────────────────────────────────────────────────────────


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    specialty: str | None = Field(default=None, max_length=120)
    hospital: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    specialty: str | None = Field(default=None, max_length=120)
    hospital: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)


class ProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    specialty: str | None
    hospital: str | None
    phone: str | None
    notes: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class AssignmentCreate(BaseModel):
    provider_id: uuid.UUID
    uhid: str | None = Field(default=None, max_length=64)


class AssignmentUpdate(BaseModel):
    uhid: str | None = Field(default=None, max_length=64)


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    specialty: str | None
    hospital: str | None
    uhid: str | None
    created_at: UTCDateTime


# ── Insurance ─────────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    insurer: str = Field(min_length=1, max_length=200)
    plan_name: str | None = Field(default=None, max_length=200)
    policy_number: str = Field(min_length=1, max_length=100)
    sum_insured: float | None = Field(default=None, ge=0)
    valid_till: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PolicyUpdate(BaseModel):
    insurer: str | None = Field(default=None, min_length=1, max_length=200)
    plan_name: str | None = Field(default=None, max_length=200)
    policy_number: str | None = Field(default=None, min_length=1, max_length=100)
    sum_insured: float | None = Field(default=None, ge=0)
    valid_till: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PolicyResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    insurer: str
    plan_name: str | None
    policy_number: str
    sum_insured: float | None
    valid_till: date | None
    notes: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class ClaimCreate(BaseModel):
    amount: float = Field(ge=0)
    claimed_on: date
    status: ClaimStatus = ClaimStatus.SUBMITTED
    description: str | None = Field(default=None, max_length=2000)


class ClaimUpdate(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    claimed_on: date | None = None
    status: ClaimStatus | None = None
    description: str | None = Field(default=None, max_length=2000)


class ClaimResponse(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    amount: float
    status: str
    claimed_on: date
    description: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


# ── Emergency card + history ──────────────────────────────────────────


class EmergencyCard(BaseModel):
    member: dict
    allergies: list[dict]
    conditions: list[dict]
    active_medications: list[dict]
    providers: list[dict]


class HistoryItem(BaseModel):
    type: Literal["record", "medication", "lab", "vital"]
    date: date
    title: str
    detail: str | None = None
    ref_id: uuid.UUID
