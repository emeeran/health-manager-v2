"""Scheduled jobs. Each opens its own session; never shares a request's.

Every job body is IDEMPOTENT and double-run-safe: tests (and APScheduler
coalescing) may invoke any body twice on the same data without duplicating
rows or raising. Cadences are registered in app/core/scheduler.py; knobs
that would normally be config fields are read from the environment with
sane defaults here (config.py is frozen for this phase).
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import env_int
from app.core.database import SessionLocal
from app.models import (
    Medication,
    RefreshToken,
    Reminder,
)
from app.services.ai.router import health_cache

logger = logging.getLogger(__name__)


async def process_reminders() -> int:
    """Fire due reminders (web push when configured); advance repeats."""
    from app.services import web_push_service

    fired = 0
    now = datetime.now(UTC).replace(tzinfo=None)
    async with SessionLocal() as db:
        due = (
            await db.scalars(
                select(Reminder).where(Reminder.done.is_(False), Reminder.remind_at <= now)
            )
        ).all()
        for reminder in due:
            title = f"Reminder: {reminder.title}"
            if web_push_service.push_configured() and reminder.member_id:
                from app.models import FamilyMember, Household

                member = await db.get(FamilyMember, reminder.member_id)
                household = (
                    await db.get(Household, member.household_id) if member is not None else None
                )
                if household is not None:
                    await web_push_service.push_to_user(
                        db, household.primary_user_id, title, reminder.title
                    )
            if reminder.repeat == "none":
                reminder.done = True
            else:
                step = {
                    "daily": timedelta(days=1),
                    "weekly": timedelta(weeks=1),
                    "monthly": timedelta(days=30),
                }.get(reminder.repeat)
                if step:
                    reminder.remind_at = reminder.remind_at + step
            fired += 1
        await db.commit()
    if fired:
        logger.info("process_reminders: fired %s", fired)
    return fired


async def prune_tokens() -> int:
    """Delete refresh tokens expired more than a day ago."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    async with SessionLocal() as db:
        result = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < cutoff))
        await db.commit()
        pruned = int(getattr(result, "rowcount", 0) or 0)
    if pruned:
        logger.info("prune_tokens: removed %s", pruned)
    return pruned


# ── Title-keyed idempotency helpers ──────────────────────────────────────
# Notification titles are EncryptedText — not queryable in SQL — so dedupe
# works by loading recent rows for the household and comparing decrypted
# titles in Python (same pattern as v1's DigestService._delivered_already).


async def _recent_titles(db, household_id, days: int = 8) -> set[str]:
    from app.core.encryption import decrypt_secret
    from app.models import Notification

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    rows = await db.scalars(
        select(Notification.title_encrypted).where(
            Notification.household_id == household_id,
            Notification.created_at >= cutoff,
        )
    )
    return {(decrypt_secret(t) or "").strip().lower() for t in rows}


async def check_refill_alerts() -> int:
    """Active medications whose end_date falls within REFILL_ALERT_DAYS
    (default 5) get a refill notification, once per medicine per window.

    Idempotent via decrypted-title dedupe against the household's recent
    notifications, so a daily cadence (or a double run) never duplicates.
    """
    from app.models import FamilyMember
    from app.services.notifications import create_notification

    threshold_days = env_int("REFILL_ALERT_DAYS", 5)
    horizon = date.today() + timedelta(days=threshold_days)
    created = 0
    async with SessionLocal() as db:
        meds = (
            await db.execute(
                select(Medication, FamilyMember.household_id)
                .join(FamilyMember, FamilyMember.id == Medication.member_id)
                .where(
                    Medication.status == "active",
                    Medication.end_date.isnot(None),
                    Medication.end_date <= horizon,
                )
            )
        ).all()
        if not meds:
            return 0

        titles_by_household: dict = {}
        for med, household_id in meds:
            titles = titles_by_household.get(household_id)
            if titles is None:
                titles = await _recent_titles(db, household_id)
                titles_by_household[household_id] = titles
            title = f"Refill due: {med.medicine}"
            if title.lower() in titles:
                continue
            titles.add(title.lower())
            end = med.end_date
            body = (
                f"{med.medicine} ends {end.isoformat()} — order a refill or review the course."
                if end is not None
                else f"{med.medicine} is ending soon — order a refill."
            )
            create_notification(db, household_id=household_id, title=title, body=body)
            created += 1
        await db.commit()
    if created:
        logger.info("check_refill_alerts: created %s notification(s)", created)
    return created


async def weekly_digest() -> int:
    """One Weekly Highlights notification per household (idempotent per ISO
    week via digest_service's title key)."""
    from app.models import Household
    from app.services import digest_service

    delivered = 0
    async with SessionLocal() as db:
        households = (await db.scalars(select(Household))).all()
        for household in households:
            if await digest_service.build_and_deliver(db, household.id):
                delivered += 1
        await db.commit()
    if delivered:
        logger.info("weekly_digest: delivered to %d household(s)", delivered)
    return delivered


async def dispatch_web_push() -> dict:
    """Push undelivered notifications to subscribed browsers, advancing each
    subscription's watermark (v1 semantics — see web_push_service)."""
    from app.services import web_push_service

    async with SessionLocal() as db:
        return await web_push_service.dispatch_pending(db)


async def check_ai_providers() -> dict[str, bool]:
    """Probe each configured AI provider, feeding a circuit-breaker cache.

    Ollama is probed via its /api/tags listing; OpenAI-compatible cloud
    providers via provider.available(). Results go into a module-level
    ProviderHealthCache so anything that reads health_cache gets the
    same short-lived negative cache the router uses. Idempotent and
    network-safe: probes never raise.
    """
    import asyncio
    import time

    from app.services.ai.router import build_plan

    checks: dict[str, bool] = {}

    async def _probe(name: str, provider) -> None:
        try:
            checks[name] = await provider.available()
        except Exception as exc:  # noqa: BLE001 — a dead provider must not fail the job
            logger.warning("%s health probe failed: %s", name, exc)
            checks[name] = False

    plan = build_plan()
    if not plan:
        return checks
    async with asyncio.timeout(30):
        await asyncio.gather(*(_probe(p.name, p) for p in plan))

    for name, ok in checks.items():
        health_cache.set(name, ok, time.monotonic())

    available = sum(1 for ok in checks.values() if ok)
    logger.info(
        "AI provider health: %d/%d available (%s)",
        available,
        len(checks),
        ", ".join(f"{n}={'OK' if ok else 'DOWN'}" for n, ok in checks.items()),
    )
    return checks


async def detect_anomalies() -> int:
    """Flag vitals outside guideline ranges (last ANOMALY_SCAN_DAYS days) as
    notifications — one per member/vital-type/day, title-keyed so re-runs
    are no-ops. Simplified port of v1's lab anomaly sweep to v2's vitals.
    """
    from app.models import FamilyMember, VitalMeasurement
    from app.core.reference_ranges import GLUCOSE_RANGES, bp_stage
    from app.services.notifications import create_notification

    window_days = env_int("ANOMALY_SCAN_DAYS", 7)
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=window_days)
    created = 0
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(VitalMeasurement, FamilyMember.household_id, FamilyMember.name)
                .join(FamilyMember, FamilyMember.id == VitalMeasurement.member_id)
                .where(VitalMeasurement.measured_at >= cutoff)
            )
        ).all()

        if not rows:
            return 0

        # Group by (household, member, type, day) → deterministic titles.
        groups: dict[tuple, dict] = {}
        for vital, household_id, member_name in rows:
            direction = _vital_direction(vital, GLUCOSE_RANGES, bp_stage)
            if not direction:
                continue
            day = (
                vital.measured_at.astimezone(UTC).date()
                if vital.measured_at.tzinfo is not None
                else vital.measured_at.date()
            )
            key = (household_id, vital.member_id, vital.vital_type, day)
            group = groups.setdefault(
                key,
                {
                    "household_id": household_id,
                    "member_name": member_name,
                    "vital_type": vital.vital_type,
                    "day": day,
                    "count": 0,
                    "direction": direction,
                    "worst": vital,
                },
            )
            group["count"] += 1
            if direction == "HIGH":  # prefer HIGH in the title
                group["direction"] = "HIGH"
                group["worst"] = vital

        titles_by_household: dict = {}
        for group in groups.values():
            title = (
                f"Vital anomaly: {group['member_name']} {group['vital_type']} "
                f"out of range on {group['day'].isoformat()}"
            )
            titles = titles_by_household.get(group["household_id"])
            if titles is None:
                titles = await _recent_titles(db, group["household_id"])
                titles_by_household[group["household_id"]] = titles
            if title.lower() in titles:
                continue
            titles.add(title.lower())
            worst = group["worst"]
            value = str(worst.value_num)
            if worst.value_secondary is not None:
                value = f"{worst.value_num}/{worst.value_secondary}"
            body = (
                f"{group['count']} reading(s) out of range "
                f"({group['direction']}, latest {value}) on "
                f"{group['day'].isoformat()}. Review the vitals trend."
            )
            create_notification(db, household_id=group["household_id"], title=title, body=body)
            created += 1
        await db.commit()
    if created:
        logger.info("detect_anomalies: created %s notification(s)", created)
    return created


def _vital_direction(vital, glucose_ranges: dict, bp_stage) -> str:
    """HIGH/LOW when the reading sits outside its guideline band, else ''."""
    vtype = vital.vital_type
    value = float(vital.value_num)
    if vtype == "blood_pressure":
        if vital.value_secondary is None:
            return ""
        stage = bp_stage(value, float(vital.value_secondary))
        if stage["label"] in ("High BP (Stage 2)", "Hypertensive crisis"):
            return "HIGH"
        if value < 90 or float(vital.value_secondary) < 50:
            return "LOW"
        return ""
    if vtype == "blood_glucose":
        ctx = vital.glucose_context or "random"
        rng = glucose_ranges.get(ctx) or glucose_ranges["post_prandial"]
        if value > rng["normal_high"]:
            return "HIGH"
        if value < rng["normal_low"]:
            return "LOW"
        return ""
    if vtype == "spo2" and value < 90:
        return "LOW"
    if vtype == "temperature":
        if value > 39.0:
            return "HIGH"
        if value < 35.0:
            return "LOW"
    if vtype == "heart_rate":
        if value > 120:
            return "HIGH"
        if value < 50:
            return "LOW"
    return ""


async def cleanup_staging() -> int:
    """Delete stale staging/upload temp files (mtime older than
    STAGING_MAX_AGE_HOURS, default 24). v2's store is content-addressed and
    has no long-lived staging area, so this sweeps data/staging plus any
    ``*.tmp`` litter under the storage root; re-running over a clean tree
    deletes nothing."""
    import time
    from pathlib import Path

    from app.core.storage import storage_root

    max_age_hours = env_int("STAGING_MAX_AGE_HOURS", 24)
    cutoff = time.time() - max_age_hours * 3600
    staging = storage_root().parent / "staging"
    candidates: list[Path] = []
    if staging.exists():
        candidates.extend(p for p in staging.iterdir() if p.is_file())
    root = storage_root()
    if root.exists():
        candidates.extend(p for p in root.rglob("*.tmp") if p.is_file())

    deleted = 0
    for path in candidates:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except OSError:
            logger.warning("Could not delete stale staging file: %s", path)
    if deleted:
        logger.info("cleanup_staging: removed %s stale file(s)", deleted)
    return deleted


async def verify_file_integrity() -> dict[str, int]:
    """Re-hash a bounded batch of the newest attachments against their
    recorded plaintext SHA-256 (content-addressed store spot-check).

    Read-only job: mismatches/missing files are counted and logged, never
    mutated — the store shares files across rows, so self-repair is unsafe.
    """
    import hashlib

    from app.core.encryption import decrypt_bytes
    from app.core.storage import storage_root
    from app.models import Attachment

    batch = env_int("INTEGRITY_BATCH", 25)
    verified = 0
    failed = 0
    async with SessionLocal() as db:
        attachments = (
            await db.scalars(select(Attachment).order_by(Attachment.created_at.desc()).limit(batch))
        ).all()
        root = storage_root()
        for att in attachments:
            path = root / att.file_path
            if not path.is_file():
                logger.warning("Integrity check: file missing for attachment %s", att.id)
                failed += 1
                continue
            try:
                actual = hashlib.sha256(decrypt_bytes(path.read_bytes())).hexdigest()
                if actual != att.content_hash:
                    logger.error(
                        "Integrity check FAILED for attachment %s: expected %s, got %s",
                        att.id,
                        att.content_hash[:12],
                        actual[:12],
                    )
                    failed += 1
                else:
                    verified += 1
            except Exception:  # noqa: BLE001
                failed += 1
                logger.exception("Integrity check error for attachment %s", att.id)
    if failed:
        logger.warning("File integrity check: %d verified, %d FAILED", verified, failed)
    else:
        logger.info("File integrity check: %d files verified OK", verified)
    return {"verified": verified, "failed": failed}


# ── Database backup (hourly tick, self-gated) ────────────────────────────


async def get_backup_schedule() -> str:
    """The primary household's backup schedule (off | daily | weekly).

    Single-household family-server assumption: the oldest household's
    settings_json drives the server-wide schedule.
    """
    import json

    from app.models import Household

    try:
        async with SessionLocal() as db:
            household = (
                await db.scalars(select(Household).order_by(Household.created_at).limit(1))
            ).first()
            if household is not None and household.settings_json:
                parsed = json.loads(household.settings_json)
                schedule = parsed.get("backup_schedule", "off")
                if isinstance(schedule, str) and schedule in ("off", "daily", "weekly"):
                    return schedule
    except Exception:  # noqa: BLE001
        logger.exception("Could not read backup schedule; defaulting to off")
    return "off"


async def backup_database() -> bool:
    """Hourly tick, gated on the household schedule + last-run state so the
    cadence can change live without rescheduling the scheduler."""
    schedule = await get_backup_schedule()
    if schedule == "off":
        return False
    interval = {"daily": 86400, "weekly": 604800}.get(schedule)
    if interval is None:
        return False
    from app.services import backup_service

    state = backup_service.read_backup_state()
    last_run = state.get("last_run")
    if isinstance(last_run, str) and last_run:
        try:
            elapsed = (datetime.now(UTC) - datetime.fromisoformat(last_run)).total_seconds()
        except ValueError:
            elapsed = interval  # corrupt timestamp → treat as due
        if elapsed < interval:
            return False
    return await run_backup_now() is not None


async def run_backup_now() -> dict | None:
    """Create one encrypted backup archive now, record state, apply the
    shared 30-day retention. Used by the gated tick and POST /backup/run."""
    import asyncio as _asyncio

    from app.services import backup_service

    archive = await _asyncio.to_thread(backup_service.create_backup)
    created = datetime.now(UTC).isoformat()
    state = backup_service.read_backup_state()
    backup_service.write_backup_state({**state, "last_run": created, "last_archive": archive.name})
    pruned = backup_service.prune_old_archives(env_int("BACKUP_RETENTION_DAYS", 30))
    try:
        size = archive.stat().st_size
    except OSError:
        size = 0
    logger.info(
        "Backup archive created: %s (%d bytes, pruned %s old)",
        archive.name,
        size,
        pruned,
    )
    return {
        "filename": archive.name,
        "size_bytes": size,
        "created_at": created,
    }


async def rotate_backups() -> int:
    """Daily: prune backup archives beyond the 30-day retention window."""
    from app.services import backup_service

    pruned = backup_service.prune_old_archives(env_int("BACKUP_RETENTION_DAYS", 30))
    if pruned:
        logger.info("rotate_backups: pruned %s archive(s)", pruned)
    return pruned
