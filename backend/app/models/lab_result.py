import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText


class LabFlag(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("health_records.id"), nullable=True, index=True
    )
    test_name: Mapped[str] = mapped_column(String(200))
    result: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    units: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_value: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    note: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Parsed numeric columns power trending/flags without re-parsing text.
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    ref_low_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    flag: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
