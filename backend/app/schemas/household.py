"""Schemas for household admin: info, users, invitations, AI config, keys."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field
from app.schemas._datetime import UTCDateTime


class HouseholdInfo(BaseModel):
    id: uuid.UUID
    name: str
    my_role: str


class HouseholdUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class HouseholdUserInfo(BaseModel):
    user_id: uuid.UUID
    username: str
    role: str
    is_primary: bool
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class RoleUpdate(BaseModel):
    role: Literal["admin", "member", "viewer"]


class InvitationCreated(BaseModel):
    id: uuid.UUID
    token: str  # shown exactly once
    role: str
    expires_at: UTCDateTime


class InvitationInfo(BaseModel):
    id: uuid.UUID
    role: str
    expires_at: UTCDateTime
    accepted: bool
    created_at: UTCDateTime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class ProviderConfig(BaseModel):
    name: str = Field(max_length=32)
    enabled: bool = True
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)


class AiConfig(BaseModel):
    # "auto" = cloud-first, "cloud"/"local" as before; a named provider
    # (e.g. "groq") floats that provider to the front of the failover plan.
    primary_provider: Literal[
        "auto",
        "cloud",
        "local",
        "openai",
        "groq",
        "gemini",
        "cohere",
        "deepseek",
        "mistral",
        "openrouter",
        "huggingface",
        "ollama",
    ] = "auto"
    providers: list[ProviderConfig] = Field(default_factory=list, max_length=8)


class ProviderKeySet(BaseModel):
    value: str = Field(min_length=1, max_length=500)


class AuditEntry(BaseModel):
    id: uuid.UUID
    action: str
    detail: str | None
    ip: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
