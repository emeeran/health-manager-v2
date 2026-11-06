"""Password hashing and JWT issue/verify."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

JWT_ISSUER = "health-manager-v2"
JWT_AUDIENCE = "health-manager-v2-web"


def hash_password(password: str) -> str:
    return str(pwd_context.hash(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bool(pwd_context.verify(password, password_hash))
    except ValueError:
        return False


def create_access_token(user_id: str) -> tuple[str, str]:
    """Return (token, jti)."""
    settings = get_settings()
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "jti": jti,
        "type": "access",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, jti


def decode_access_token(token: str) -> dict | None:
    """Return claims or None if invalid/expired."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        return None
