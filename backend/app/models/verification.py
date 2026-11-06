import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    PASSED = "passed"
    FLAGGED = "flagged"
    FAILED = "failed"


class Verification(Base):
    """Second-model verification of an AI artefact (extraction, report…)."""

    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    subject_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=VerificationStatus.PENDING.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Claim-level audit detail (quotes PHI, so encrypted like notes).
    audit_json: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    verifier_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # what was checked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
