"""TOTP 2FA: setup (secret + QR + one-time backup codes), verify, disable.

Secrets and backup codes are Fernet-encrypted at rest (encrypt_secret).
Backup codes are single-use, stored as a JSON list of {hash, used} rows —
plain codes are shown once at setup.
"""

import hashlib
import json
import secrets

import pyotp
import qrcode
import qrcode.image.pil
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import User

BACKUP_CODE_COUNT = 8


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def generate_backup_codes() -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(BACKUP_CODE_COUNT)]


def qr_data_url(secret: str, username: str) -> str:
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name="Family Health Manager v2"
    )
    img = qrcode.make(uri, image_factory=qrcode.image.pil.PilImage)
    import io
    import base64

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def setup(db: AsyncSession, user: User) -> dict:
    secret = pyotp.random_base32()
    codes = generate_backup_codes()
    user.totp_secret = encrypt_secret(secret)
    user.backup_codes = encrypt_secret(json.dumps([{"hash": _hash_code(c)} for c in codes]))
    user.totp_enabled = False  # enabled only after verify
    return {
        "secret": secret,
        "qr_data_url": qr_data_url(secret, user.username),
        "backup_codes": codes,
    }


def _totp(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret)


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret:
        return False
    secret = decrypt_secret(user.totp_secret)
    if not secret:
        return False
    return bool(_totp(secret).verify(code.strip(), valid_window=1))


def verify_backup_code(db: AsyncSession, user: User, code: str) -> bool:
    if not user.backup_codes:
        return False
    raw = decrypt_secret(user.backup_codes)
    if not raw:
        return False
    entries = json.loads(raw)
    target = _hash_code(code.strip())
    for entry in entries:
        if entry["hash"] == target and not entry.get("used"):
            entry["used"] = True
            user.backup_codes = encrypt_secret(json.dumps(entries))
            return True
    return False


def confirm_enable(db: AsyncSession, user: User, code: str) -> bool:
    if verify_totp(user, code):
        user.totp_enabled = True
        return True
    return False


def disable(db: AsyncSession, user: User, code: str) -> bool:
    if not user.totp_enabled:
        return False
    if verify_totp(user, code) or verify_backup_code(db, user, code):
        user.totp_enabled = False
        user.totp_secret = None
        user.backup_codes = None
        return True
    return False
