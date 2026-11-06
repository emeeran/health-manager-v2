import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import EncryptedText


class PreventiveDismissal(Base):
    """One dismissed preventive-care recommendation for one family member.

    Recommendations are recomputed on every request from deterministic rules,
    so "not now" has to be stored: the rec_key (a stable title slug) is hidden
    until it is un-dismissed.
    """

    __tablename__ = "preventive_dismissals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    # Slugified recommendation title ("annual-physical-exam") — stable across
    # restarts because the rule set is defined as literals in the service.
    rec_key: Mapped[str] = mapped_column(String(200), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Optional free-text reason (PHI — encrypted at rest).
    note: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)

    __table_args__ = (UniqueConstraint("member_id", "rec_key", name="uq_preventive_member_key"),)
