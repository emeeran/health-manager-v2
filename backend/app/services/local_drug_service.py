"""Local drug catalog: name normalization, composition parsing, CSV seeding.

The bundled CSV (``app/data/jan_aushadhi_products.csv``) is the official
Jan Aushadhi (PMBJP) product list — fetched from the Jan Aushadhi portal's
product API (guest token → POST /api/v1/website/getAllProductForWeb) and
saved with columns ``productId,genericName,groupName,drugCode,unitSize,mrp,
status,serialNo``. Refresh by exporting a fresher list and re-running::

    uv run python -m app.scripts.seed_jan_aushadhi [path/to/products.csv]

Legacy sample-shaped CSVs (``product_id,name,composition,price,…``) are
also accepted so composition-parsing fixtures keep working.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.local_drug import LocalDrug

logger = logging.getLogger(__name__)

CATALOG_CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "jan_aushadhi_products.csv"

# Dosage tokens stripped during normalization ("500mg", "0.5 mcg").
_DOSAGE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|ug|ml|gm|g|iu|meq|%|units?)\b", re.I)

# Form words / pack modifiers dropped during normalization.
_FORM_WORDS = {
    "tab",
    "tabs",
    "tablet",
    "tablets",
    "cap",
    "caps",
    "capsule",
    "capsules",
    "syp",
    "syrup",
    "inj",
    "injection",
    "drops",
    "drop",
    "cream",
    "ointment",
    "gel",
    "inhaler",
    "puff",
    "spray",
    "suspension",
    "susp",
    "strip",
    "sachet",
    "pr",
    "sr",
    "er",
    "xr",
    "ds",
    "ip",
    "powder",
}

# One ingredient entry: a name + an optional parenthesized strength.
_INGREDIENT_RE = re.compile(r"^\s*([A-Za-z][A-Za-z\- ']*)\s*(?:\(([^)]*)\))?\s*$")


def normalize_drug_name(name: str | None) -> str:
    """Matching form: lowercase, dosage/form words stripped, single-spaced.

    e.g. "Metformin 500mg Tablet IP" → "metformin". Empty for blank input.
    """
    if not name:
        return ""
    s = re.sub(r"\([^)]*\)", " ", name.lower())
    s = _DOSAGE_RE.sub(" ", s)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    words = [w for w in s.split() if w and w not in _FORM_WORDS]
    return " ".join(words).strip()


def parse_composition(composition: str | None) -> list[dict]:
    """Composition string → ``[{"name", "strength"}]``.

    Handles "Metformin (500mg)" and combinations joined by "+" / ",".
    """
    if not composition or not composition.strip():
        return []
    out: list[dict] = []
    for part in re.split(r"\s*[+,]\s*", composition):
        part = part.strip()
        if not part:
            continue
        match = _INGREDIENT_RE.match(part)
        if not match:
            continue
        name = match.group(1).strip()
        if not name:
            continue
        strength = (match.group(2) or "").strip() or None
        out.append({"name": name, "strength": strength})
    return out


def ingredient_names(ingredients_json: str | None, composition: str | None = None) -> list[str]:
    """Distinct ingredient display names from stored JSON (or raw composition)."""
    if ingredients_json:
        try:
            parsed = json.loads(ingredients_json)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            names = [str(i.get("name")) for i in parsed if isinstance(i, dict) and i.get("name")]
            if names:
                return names
    return [ing["name"] for ing in parse_composition(composition)]


def parsed_ingredients(drug: LocalDrug) -> list[dict]:
    """Structured ingredients for a catalog row: [{"name", "strength"}].

    Falls back to the raw composition text when the stored JSON is missing
    or corrupt — allergy-conflict matching needs names, not prose.
    """
    if drug.ingredients:
        try:
            parsed = json.loads(drug.ingredients)
        except (ValueError, TypeError):
            parsed = None
        if (
            isinstance(parsed, list)
            and parsed
            and all(isinstance(i, dict) and i.get("name") for i in parsed)
        ):
            return parsed
    return parse_composition(drug.composition)


def _rows_from_csv(path: Path) -> list[dict]:
    """Normalize both supported CSV shapes into the seeder's row dict.

    Official PMBJP export: productId/genericName/unitSize/mrp (no
    composition). Legacy sample shape: product_id/name/composition/price/….
    """
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for row in csv.DictReader(handle):
            name = (row.get("name") or row.get("genericName") or "").strip()
            rows.append(
                {
                    "product_id": (row.get("product_id") or row.get("productId") or "").strip(),
                    "name": name,
                    "manufacturer": (row.get("manufacturer") or "").strip() or None,
                    "composition": (row.get("composition") or "").strip() or None,
                    "price": _parse_price(row.get("price") or row.get("mrp")),
                    "product_form": (row.get("product_form") or "").strip() or None,
                    "package": (row.get("package") or row.get("unitSize") or "").strip() or None,
                }
            )
        return rows


def _parse_price(raw: str | None) -> float | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return round(float(str(raw).strip().rstrip("₹")), 2)
    except ValueError:
        return None


async def seed_local_drugs(db: AsyncSession, csv_path: Path | None = None) -> int:
    """Upsert catalog rows from the bundled CSV. Returns rows seeded.

    Upsert identity is ``product_id`` (stable catalog key); re-running the
    seeder refreshes prices/compositions in place.
    """
    path = csv_path or CATALOG_CSV_PATH
    rows = _rows_from_csv(path)
    seeded = 0
    for row in rows:
        if not row["product_id"] or not row["name"]:
            continue
        existing = (
            await db.execute(select(LocalDrug).where(LocalDrug.product_id == row["product_id"]))
        ).scalar_one_or_none()
        ingredients = parse_composition(row["composition"])
        values = {
            "name": row["name"],
            "name_normalized": normalize_drug_name(row["name"]),
            "manufacturer": row["manufacturer"],
            "composition": row["composition"],
            "ingredients": json.dumps(ingredients) if ingredients else None,
            "price": row["price"],
            "product_form": row["product_form"],
            "package": row["package"],
        }
        if existing is None:
            db.add(LocalDrug(product_id=row["product_id"], **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        seeded += 1
    await db.flush()
    return seeded


async def search_local_drugs(db: AsyncSession, query: str, limit: int = 20) -> list[LocalDrug]:
    """Catalog rows whose normalized name contains the normalized query."""
    needle = normalize_drug_name(query)
    if not needle:
        return []
    rows = await db.scalars(
        select(LocalDrug)
        .where(LocalDrug.name_normalized.contains(needle, autoescape=True))
        .order_by(LocalDrug.name.asc())
        .limit(limit)
    )
    return list(rows)
