"""SymptomEntry model — the symptom journal.

``symptom`` stays plaintext (like Allergy.substance) — it's the indexed
lookup key the correlation engine groups by; notes and free-text context
are PHI and encrypted.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText


class SymptomSeverity(str, enum.Enum):
    """Journal symptom intensity."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class SymptomEntry(Base):
    """One logged symptom occurrence for a family member."""

    __tablename__ = "symptom_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    symptom: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(16), default=SymptomSeverity.MODERATE.value)
    started_at: Mapped[date] = mapped_column(Date)
    resolved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Free-text notes: what it felt like, suspected triggers (food, stress…).
    notes: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_symptoms_member_symptom", "member_id", "symptom"),
        Index("ix_symptoms_member_started", "member_id", "started_at"),
    )
