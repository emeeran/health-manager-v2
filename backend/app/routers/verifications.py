"""Verification polling endpoint (extraction verdicts + claim audits)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User, Verification
from app.services.ai.agents.contracts import AuditReport

router = APIRouter(prefix="/verifications", tags=["verifications"])


class VerificationResponse(BaseModel):
    id: uuid.UUID
    subject_type: str
    status: str
    notes: str | None
    verifier_name: str | None
    # Claim table for the audit agent; null for extraction-only verdicts.
    audit: AuditReport | None = None


def _audit(row: Verification) -> AuditReport | None:
    if not row.audit_json:
        return None
    try:
        return AuditReport.model_validate_json(row.audit_json)
    except ValueError:
        return None


def _view(row: Verification) -> VerificationResponse:
    return VerificationResponse(
        id=row.id,
        subject_type=row.subject_type,
        status=row.status,
        notes=row.notes,
        verifier_name=row.verifier_name,
        audit=_audit(row),
    )


@router.get("/{verification_id}", response_model=VerificationResponse)
async def get_verification(
    verification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerificationResponse:
    row = await db.get(Verification, verification_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    await get_scoped_member(row.member_id, user, db)
    return _view(row)
