"""Security audit trail helper: best-effort writes for sensitive actions.

`record_audit` only stages the row — the endpoint's `get_db` commit (or an
explicit commit) persists it. Detail text is Fernet-encrypted at rest.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_secret
from app.models import SecurityAudit


def record_audit(
    db: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    household_id: uuid.UUID | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        SecurityAudit(
            action=action,
            user_id=user_id,
            household_id=household_id,
            detail=encrypt_secret(detail),
            ip=ip,
        )
    )
