import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrawlerDrug(Base):
    """One crawled pharmacy-catalog entry (1mg / Apollo Pharmacy).

    Synced from the external crawler's checkpoint SQLite
    (``MEDICINE_CRAWLER_DATA_DIR/crawl.db``, table ``rows``) — upsert identity
    is the source page URL, so re-syncs refresh prices in place. Powers
    pharmacy price offers alongside the Jan Aushadhi generic catalog. Rows are
    factual listings — never a purchase channel.
    """

    __tablename__ = "crawler_drugs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Source page URL — stable upsert identity for re-syncing.
    url: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    # "1mg" | "apollo"
    source: Mapped[str] = mapped_column(String(20), index=True)
    brand_name: Mapped[str] = mapped_column(String(300))
    # Normalized matching key (dosage/form words stripped) — search + joins.
    name_normalized: Mapped[str] = mapped_column(String(300), index=True)
    generic_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pack_size: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(60), nullable=True)
    price_mrp: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_selling: Mapped[float | None] = mapped_column(Float, nullable=True)
    uses: Mapped[str | None] = mapped_column(Text, nullable=True)
    side_effects: Mapped[str | None] = mapped_column(Text, nullable=True)
    therapeutic_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prescription_required: Mapped[str | None] = mapped_column(String(10), nullable=True)
    category_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_crawler_drugs_name_norm", "name_normalized"),)
