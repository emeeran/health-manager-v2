import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText


class ClaimStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SETTLED = "settled"


class InsurancePolicy(Base):
    """An insurance policy covering one family member.

    Policy numbers are identifiers tied to PHI — encrypted at rest.
    """

    __tablename__ = "insurance_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    insurer: Mapped[str] = mapped_column(String(200))
    plan_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    policy_number: Mapped[str] = mapped_column(EncryptedText)
    sum_insured: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    valid_till: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InsuranceClaim(Base):
    """A claim filed against a policy, tracked to settlement."""

    __tablename__ = "insurance_claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("insurance_policies.id"), index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(16), default=ClaimStatus.SUBMITTED.value, index=True)
    claimed_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
