import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSecret(Base):
    """Runtime-stored credential (e.g. cloud provider keys), Fernet-encrypted.

    Resolution order: app_secrets row first, env fallback — so per-install
    keys set through the UI beat whatever the process environment holds.
    """

    __tablename__ = "app_secrets"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_encrypted: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
