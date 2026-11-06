import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LocalDrug(Base):
    """One curated drug-catalog entry (brand → composition + price).

    Seeded from the bundled Jan Aushadhi CSV (``app/data/jan_aushadhi.csv``)
    via :func:`app.services.local_drug_service.seed_local_drugs`. Powers the
    ``/drugs/search`` endpoint that later feeds allergy-conflict ingredient
    matching. The bundled CSV is a small representative sample — the full
    government catalog is an external data dependency, refreshed by re-seeding.
    """

    __tablename__ = "local_drugs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Stable catalog key — upsert identity for re-seeding.
    product_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    # Normalized matching key (dosage/form words stripped) — search + joins.
    name_normalized: Mapped[str] = mapped_column(String(300), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Raw composition string ("Metformin (500mg) + Glimepiride (0.5mg)").
    composition: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Parsed composition as JSON: [{"name": "...", "strength": "..."}].
    ingredients: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    product_form: Mapped[str | None] = mapped_column(String(60), nullable=True)
    package: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_local_drugs_name_norm", "name_normalized"),)
