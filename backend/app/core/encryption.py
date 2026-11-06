"""Fernet encryption at rest.

Primary key: ENCRYPTION_KEY verbatim (urlsafe base64, 32 bytes).
Fallback (dev only): PBKDF2-derived from SECRET_KEY with a static salt, so a
fresh clone needs only SECRET_KEY. Decryption tries primary then fallback so
rotating to a dedicated key stays backwards compatible.
"""

import base64
import functools

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

_DERIVED_SALT = b"health-manager-v2-encryption-salt-v1"


@functools.lru_cache
def _fernet_instances() -> list[Fernet]:
    settings = get_settings()
    instances: list[Fernet] = []
    if settings.ENCRYPTION_KEY:
        instances.append(Fernet(settings.ENCRYPTION_KEY.encode()))
    if settings.SECRET_KEY:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_DERIVED_SALT,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
        instances.append(Fernet(key))
    if not instances:
        raise RuntimeError("Set SECRET_KEY (and optionally ENCRYPTION_KEY) first.")
    return instances


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt a short value for a DB column. None/'' pass through."""
    if not plaintext:
        return plaintext
    token = _fernet_instances()[0].encrypt(plaintext.encode())
    return token.decode()


def decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a column value; legacy plaintext reads through unchanged."""
    if not ciphertext:
        return ciphertext
    for fernet in _fernet_instances():
        try:
            return fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            continue
    # Not encrypted by any known key — assume legacy plaintext.
    return ciphertext


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw bytes (files at rest). Primary key only — anything we
    write, we read with the same key; legacy keys apply to DB columns."""
    return _fernet_instances()[0].encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    try:
        return _fernet_instances()[0].decrypt(data)
    except InvalidToken:
        for fernet in _fernet_instances()[1:]:
            try:
                return fernet.decrypt(data)
            except InvalidToken:
                continue
    raise InvalidToken("Not decryptable with any known key")
