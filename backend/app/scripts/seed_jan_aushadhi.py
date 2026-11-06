"""Seed the local drug catalog from a Jan Aushadhi (PMBJP) product CSV.

The bundled ``app/data/jan_aushadhi_products.csv`` is the official PMBJP
export (portal product API: guest token → POST
``/api/v1/website/getAllProductForWeb``). To refresh with a newer export,
fetch the CSV from the portal and pass its path (or set
``JAN_AUSHADHI_CSV``)::

    uv run python -m app.scripts.seed_jan_aushadhi [path/to/products.csv]

Idempotent — upserts by ``product_id``, so re-running with a fresher
export updates prices and adds new products in place.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.services import local_drug_service

logger = logging.getLogger(__name__)


def _resolve_csv_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    configured = os.environ.get("JAN_AUSHADHI_CSV")
    if configured:
        return Path(configured)
    return local_drug_service.CATALOG_CSV_PATH


async def run(csv_path: Path, db: AsyncSession | None = None) -> int:
    """Seed via the service (db injectable for tests); returns rows seeded."""
    if db is not None:
        return await local_drug_service.seed_local_drugs(db, csv_path)
    async with SessionLocal() as session:
        seeded = await local_drug_service.seed_local_drugs(session, csv_path)
        await session.commit()
        return seeded


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    csv_path = _resolve_csv_path(argv[1] if len(argv) > 1 else None)
    if not csv_path.is_file():
        print(f"Catalog CSV not found: {csv_path}", file=sys.stderr)
        return 1
    seeded = asyncio.run(run(csv_path))
    print(f"Seeded {seeded} products from {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
