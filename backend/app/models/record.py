import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import EncryptedText


class RecordType(str, enum.Enum):
    DOCTOR_VISIT = "doctor_visit"
    LAB_REPORT = "lab_report"
    PRESCRIPTION = "prescription"
    DISCHARGE_SUMMARY = "discharge_summary"
    IMAGING = "imaging"
    VACCINATION = "vaccination"
    OTHER = "other"


class HealthRecord(Base):
    __tablename__ = "health_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    record_type: Mapped[str] = mapped_column(String(32), default=RecordType.OTHER.value, index=True)
    record_date: Mapped[date] = mapped_column(Date)
    record_time: Mapped[time | None] = mapped_column(nullable=True)
    # Extracted structured payload (JSON string) — PHI, encrypted at rest.
    clinical_data: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Investigative studies ordered/ performed (X-ray, CBC, …) — the new-record
    # form's Investigations field.
    investigations: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    prescription_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    summary: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    doctor_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Optional link into the household provider directory.
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Optional problem-list episode link (Phase 10 conditions).
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("condition_episodes.id"), nullable=True
    )
    # household | caregiver | private — role-ceiling enforced at read time.
    confidentiality_level: Mapped[str] = mapped_column(String(16), default="household", index=True)
    # Plaintext SHA-256 of record content for duplicate detection (Phase 10).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Set when this record was merged away into another one (dedup/merge).
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    member = relationship("FamilyMember")
    attachments = relationship(
        "Attachment",
        back_populates="record",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
