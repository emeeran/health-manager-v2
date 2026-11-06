import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import EncryptedText


class Attachment(Base):
    """Points into the content-addressable store.

    file_path is relative to STORAGE_PATH and may be shared by several
    Attachment rows (dedup by plaintext SHA-256). content_hash is of the
    PLAINTEXT so dedup/integrity work despite encryption.
    """

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("health_records.id"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(100))
    original_name: Mapped[str] = mapped_column(EncryptedText)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    record = relationship("HealthRecord", back_populates="attachments")
