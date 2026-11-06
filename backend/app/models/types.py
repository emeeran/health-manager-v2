"""Custom column types.

EncryptedText: Fernet-encrypt on bind, decrypt on result. None/'' pass
through; values that fail to decrypt under any known key are returned
as-is so legacy plaintext rows keep reading (mirrors upstream behaviour,
making the encryption migration non-breaking).
"""

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.encryption import decrypt_secret, encrypt_secret


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ARG002
        if value is None or value == "":
            return value
        return encrypt_secret(str(value))

    def process_result_value(self, value, dialect):  # noqa: ANN001, ARG002
        if value is None or value == "":
            return value
        return decrypt_secret(value)
