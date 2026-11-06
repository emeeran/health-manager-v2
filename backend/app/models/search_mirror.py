"""Cross-member search mirror (Phase 10, ported from v1 Wave 3.8).

A plaintext digest of the household's searchable entities, maintained as
derived state: ``reindex_all`` rebuilds it from the domain tables and the
FTS5 virtual table (created lazily — SQLAlchemy models cannot express
virtual tables for create_all). Privacy note: mirror ``body`` text is
plaintext PHI by design (same trust domain as the rest of the DB); never
log it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SearchMirror(Base):
    __tablename__ = "search_mirror"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Entity kind: record | medication | lab | vital | condition |
    # allergy | symptom (vaccinations are not mirrored).
    row_type: Mapped[str] = mapped_column(String(32), index=True)
    row_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("family_members.id"), index=True
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("households.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
