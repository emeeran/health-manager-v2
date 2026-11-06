import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MilestoneAchievement(Base):
    """A developmental milestone a child has reached (one row per milestone)."""

    __tablename__ = "milestone_achievements"
    __table_args__ = (
        UniqueConstraint("member_id", "milestone_key", name="uq_milestone_member_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    milestone_key: Mapped[str] = mapped_column(String(64))
    achieved_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
