import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VitalType(str, enum.Enum):
    BLOOD_PRESSURE = "blood_pressure"
    BLOOD_GLUCOSE = "blood_glucose"
    WEIGHT = "weight"
    HEIGHT = "height"
    HEAD_CIRCUMFERENCE = "head_circumference"
    TEMPERATURE = "temperature"
    HEART_RATE = "heart_rate"
    SPO2 = "spo2"
    BMI = "bmi"
    HBA1C = "hba1c"


class GlucoseContext(str, enum.Enum):
    FASTING = "fasting"
    POST_PRANDIAL = "post_prandial"
    RANDOM = "random"


class VitalMeasurement(Base):
    __tablename__ = "vital_measurements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("health_records.id"), nullable=True, index=True
    )
    vital_type: Mapped[str] = mapped_column(String(32), index=True)
    # value_secondary carries the diastolic value for blood_pressure.
    value_num: Mapped[float] = mapped_column(Float)
    value_secondary: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    glucose_context: Mapped[str | None] = mapped_column(String(20), nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
