"""Database integrity card (Phase 10, ported from v1's db_maintenance).

Read-only scan that answers three questions for the Data tab:

1. **Structural integrity** — SQLite's ``PRAGMA integrity_check`` run
   through the request's own async connection (aiosqlite supports PRAGMA
   as a plain query; PostgreSQL reports ok server-side).
2. **Orphan scan** — informational counts of rows that reference a
   missing family member, missing record, or missing condition episode.
   Never affects ``ok``: they are data hygiene, not corruption.
3. **Attachment spot-check** — a bounded sample of attachment rows is
   checked for existence under STORAGE_PATH (content-addressable store,
   so file_path may be shared by several rows).

Everything runs on the caller's session — no second connection, no
writes, safe for any authenticated user.
"""

import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.storage import storage_root

logger = logging.getLogger(__name__)

# (table, column) pairs whose member_id must point at an existing member.
_MEMBER_FK_TABLES = (
    "health_records",
    "vital_measurements",
    "lab_results",
    "medications",
    "allergies",
    "condition_episodes",
    "insurance_policies",
    "reminders",
)

# (table, column, target table) pairs with an explicit FK target.
_FK_CHECKS = (
    ("attachments", "record_id", "health_records"),
    ("lab_results", "record_id", "health_records"),
    ("medications", "record_id", "health_records"),
    ("vital_measurements", "record_id", "health_records"),
    ("medications", "condition_id", "condition_episodes"),
    ("health_records", "condition_id", "condition_episodes"),
)

ATTACHMENT_SAMPLE_LIMIT = 25


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


async def _count_orphans(db: AsyncSession, table: str, column: str, target: str) -> dict:
    sql = (
        f"SELECT count(*) FROM {_quote(table)} "
        f"LEFT JOIN {_quote(target)} ON {_quote(target)}.id = {_quote(table)}.{_quote(column)} "
        f"WHERE {_quote(table)}.{_quote(column)} IS NOT NULL AND {_quote(target)}.id IS NULL"
    )
    count = (await db.execute(text(sql))).scalar_one()
    return {"table": table, "column": column, "references": target, "count": count}


async def check_integrity(db: AsyncSession) -> dict:
    """Full read-only integrity report for the caller's database."""
    started = time.perf_counter()
    engine = db.bind.dialect.name if db.bind is not None else "sqlite"

    integrity: list[str] = ["ok"]
    orphans: list[dict] = []
    notes: list[str] = []
    ok = True

    if engine == "sqlite":
        raw = await db.execute(text("PRAGMA integrity_check"))
        integrity = [row[0] for row in raw]
        ok = integrity == ["ok"]
        if not ok:
            notes.append(
                "Structural integrity check reported problems — review the messages below."
            )
    else:
        notes.append(
            "The database engine enforces structural integrity server-side; "
            "this scan verifies tables and references are readable."
        )

    existing = set(Base.metadata.tables)
    for table in _MEMBER_FK_TABLES:
        if table not in existing:
            continue
        try:
            orphans.append(await _count_orphans(db, table, "member_id", "family_members"))
        except Exception as exc:  # noqa: BLE001 — a missing table is informational
            logger.warning("Orphan scan skipped %s: %s", table, exc)

    for table, column, target in _FK_CHECKS:
        if table not in existing or target not in existing:
            continue
        try:
            orphans.append(await _count_orphans(db, table, column, target))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Orphan scan skipped %s.%s: %s", table, column, exc)

    from sqlalchemy import select

    from app.models import Attachment

    paths = (
        (await db.execute(select(Attachment.file_path).limit(ATTACHMENT_SAMPLE_LIMIT)))
        .scalars()
        .all()
    )
    root = storage_root()
    missing = []
    for path in paths:
        if not (root / path).exists():
            missing.append(path)
    attachment_check = {
        "checked": len(paths),
        "missing": len(missing),
        "missing_paths": missing[:5],
        "sample_limit": ATTACHMENT_SAMPLE_LIMIT,
    }
    if missing:
        notes.append(f"{len(missing)} sampled attachment file(s) are missing from storage.")

    return {
        "ok": ok,
        "engine": engine,
        "integrity_check": integrity,
        "orphans": orphans,
        "orphan_count": sum(o["count"] for o in orphans),
        "attachment_check": attachment_check,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "notes": notes,
    }
