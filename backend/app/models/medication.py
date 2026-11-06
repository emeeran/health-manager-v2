import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText


class MedicationStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("health_records.id"), nullable=True, index=True
    )
    medicine: Mapped[str] = mapped_column(String(200))
    # Normalized dedup key (lowercase, alnum) for adherence + duplicate checks.
    medicine_key: Mapped[str] = mapped_column(String(200), index=True)
    # Presentation form: Tab | Cap | Inj | Syp | Cream | Drops | Inhaler | Other.
    dose_form: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timing: Mapped[str | None] = mapped_column(String(200), nullable=True)
    duration_days: Mapped[int | None] = mapped_column(nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=MedicationStatus.ACTIVE.value, index=True
    )
    # daily | prn | taper | cycle — params live in schedule_json.
    schedule_type: Mapped[str] = mapped_column(String(16), default="daily")
    schedule_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional problem-list episode link (Phase 10 conditions).
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("condition_episodes.id"), nullable=True
    )
    provider_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    notes: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def normalize_medicine_key(medicine: str) -> str:
    """Canonical key for dedup: lowercase, alphanumerics only."""
    return "".join(ch for ch in medicine.lower() if ch.isalnum())
