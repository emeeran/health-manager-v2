"""HealthAlert model — per-record lab anomaly alerts created after extraction."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText

# alert_type values (kept as plain strings — new types arrive with features).
ALERT_TYPE_LAB_ANOMALY = "lab_anomaly"
# severity values
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


class HealthAlert(Base):
    """A proactive alert, e.g. a flagged lab value found during extraction."""

    __tablename__ = "health_alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("health_records.id"), nullable=True, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(32), default=ALERT_TYPE_LAB_ANOMALY)
    severity: Mapped[str] = mapped_column(String(16), default=SEVERITY_WARNING)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(EncryptedText)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
