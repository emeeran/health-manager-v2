import uuid

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    household_name: str = Field(default="My Household", max_length=120)


class LoginRequest(BaseModel):
    username: str
    password: str
    code: str | None = None  # TOTP or backup code when 2FA is enabled


class TwoFactorLoginRequest(BaseModel):
    username: str
    password: str
    code: str


class TwoFactorCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str

    model_config = {"from_attributes": True}


class AuthResponse(UserResponse):
    pass
