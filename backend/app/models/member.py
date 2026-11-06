import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from app.core.database import Base
from app.models.base import Relationship
from app.models.types import EncryptedText


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("households.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    relationship: Mapped[str] = mapped_column(String(16), default=Relationship.SELF.value)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # male | female | other — drives CDC growth-table sex selection.
    sex: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # False forces local-only AI for this member: PHI never egresses.
    cloud_ai_consent: Mapped[bool] = mapped_column(default=True)
    # Explicit opt-in for the audit agent's external fact-checking. The
    # query is redacted in code; default False so nothing leaves the box
    # without a recorded consent decision.
    web_factcheck_consent: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Phase 9 people breadth — contact/ICE fields (PHI, encrypted at rest).
    phone: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    medical_history: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    family_medical_history: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Free-text list of medicines the member is currently on — may include
    # OTC/supplements not tracked as Medication rows. Refreshed from the
    # "update current medications?" prompt when a prescription is filed.
    current_medications: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(8), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    household = orm_relationship("Household", back_populates="members")
