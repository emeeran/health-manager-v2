"""Weekly digest — one proactive "Highlights" notification per household.

Port of the v1 digest_service core, simplified to what v2 tracks: health
records added and vitals logged in the last 7 days.
Text-only — no AI, no network. Delivered as a single Notification row;
idempotent per ISO week (title-keyed), so a re-run never duplicates.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.models import (
    FamilyMember,
    HealthRecord,
    Notification,
    VitalMeasurement,
)

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 7


@dataclass
class Digest:
    """One household's highlights for the week."""

    household_id: UUID
    items: list[dict] = field(default_factory=list)

    def add(self, section: str, text: str) -> None:
        self.items.append({"section": section, "text": text})

    def __bool__(self) -> bool:
        return bool(self.items)

    def render(self) -> str:
        """Plain-text rendering for the notification body."""
        by_section: dict[str, list[str]] = {}
        for item in self.items:
            by_section.setdefault(item["section"], []).append(f"• {item['text']}")
        return "\n".join(
            f"{section}:\n" + "\n".join(lines) for section, lines in by_section.items()
        )


def digest_title(today: date | None = None) -> str:
    """Deterministic per-ISO-week title — the idempotency key."""
    iso_year, iso_week, _ = (today or date.today()).isocalendar()
    return f"Weekly health digest — {iso_year} W{iso_week:02d}"


async def _delivered_already(db: AsyncSession, household_id: UUID, title: str) -> bool:
    """Notification titles are EncryptedText — not queryable in SQL. Load the
    household's recent notifications and compare decrypted titles in Python."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    rows = await db.scalars(
        select(Notification.title_encrypted).where(
            Notification.household_id == household_id,
            Notification.created_at >= cutoff,
        )
    )
    needle = title.strip().lower()
    return any(needle in (decrypt_secret(t) or "").lower() for t in rows)


async def build(db: AsyncSession, household_id: UUID) -> Digest:
    """Collect the week's highlights for one household."""
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=LOOKBACK_DAYS)
    digest = Digest(household_id=household_id)

    member_ids = (
        await db.scalars(select(FamilyMember.id).where(FamilyMember.household_id == household_id))
    ).all()
    if not member_ids:
        return digest

    records = await db.scalar(
        select(func.count())
        .select_from(HealthRecord)
        .where(
            HealthRecord.member_id.in_(member_ids),
            HealthRecord.is_deleted.is_(False),
            HealthRecord.created_at >= since,
        )
    )
    if records:
        digest.add("Records", f"{records} new health record(s) added")

    vitals = await db.scalar(
        select(func.count())
        .select_from(VitalMeasurement)
        .where(
            VitalMeasurement.member_id.in_(member_ids),
            VitalMeasurement.created_at >= since,
        )
    )
    if vitals:
        digest.add("Vitals", f"{vitals} vital reading(s) logged")

    return digest


async def deliver(db: AsyncSession, digest: Digest) -> bool:
    """Deliver as a single notification; idempotent per ISO week."""
    if not digest:
        return False
    title = digest_title()
    if await _delivered_already(db, digest.household_id, title):
        return False
    from app.services.notifications import create_notification

    create_notification(db, household_id=digest.household_id, title=title, body=digest.render())
    return True


async def build_and_deliver(db: AsyncSession, household_id: UUID) -> bool:
    digest = await build(db, household_id)
    delivered = await deliver(db, digest)
    if delivered:
        logger.info("Weekly digest delivered to household %s", household_id)
    return delivered
