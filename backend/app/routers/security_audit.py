"""Audit log: admin-only read access to the security audit trail."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_household_admin
from app.core.encryption import decrypt_secret
from app.models import SecurityAudit
from app.schemas.household import AuditEntry

router = APIRouter(prefix="/security-audit", tags=["audit"])


@router.get("", response_model=list[AuditEntry])
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    _: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEntry]:
    household, _ = _
    rows = (
        await db.scalars(
            select(SecurityAudit)
            .where(SecurityAudit.household_id == household.id)
            .order_by(SecurityAudit.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        AuditEntry(
            id=row.id,
            action=row.action,
            detail=decrypt_secret(row.detail),
            ip=row.ip,
            created_at=row.created_at,
        )
        for row in rows
    ]
