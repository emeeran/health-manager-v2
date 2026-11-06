"""APScheduler wiring. Started in the app lifespan; RUN_SCHEDULER=off
disables entirely (tests run job bodies directly).

Single-instance guard: under multi-worker deployments the lifespan — and
therefore ``start_scheduler`` — runs in every worker. An exclusive ``fcntl``
lock on ``data/scheduler.lock`` ensures only the winning worker starts the
periodic jobs; the loser logs and returns None. The lock is per-process
(released automatically on crash/exit) and the data/ dir is created lazily,
so importing this module never touches the filesystem.
"""

import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import env_int, get_settings

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None
_lock_fd = None

try:  # POSIX-only; the deployment target is Linux.
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover — non-POSIX dev
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False


def _try_acquire_scheduler_lock() -> bool:
    """Try to grab the single-instance scheduler lock. True if won.

    The data/ dir + lock file are created lazily here (never at import), so
    tests that never start the scheduler don't need the path. Losing the
    lock is a skip-and-log, not an error. Any unexpected failure is logged
    and the scheduler still runs — locking is an optimisation, not a hard
    requirement to serve traffic.
    """
    global _lock_fd
    if not _HAS_FCNTL:  # pragma: no cover
        return True
    try:
        Path("data").mkdir(parents=True, exist_ok=True)
        fd = open(Path("data") / "scheduler.lock", "w")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fd.close()
            return False
        _lock_fd = fd
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Could not acquire scheduler lock — running unlocked")
        return True


def _release_scheduler_lock() -> None:
    global _lock_fd
    if _lock_fd is not None:
        try:
            _lock_fd.close()
        except OSError:
            pass
        _lock_fd = None


def start_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    settings = get_settings()
    if not settings.RUN_SCHEDULER:
        logger.info("scheduler disabled (RUN_SCHEDULER=false)")
        return None

    if not _try_acquire_scheduler_lock():
        logger.info("scheduler not started — another worker owns the lock")
        return None

    from app.core import jobs

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        jobs.process_reminders,
        "interval",
        seconds=settings.REMINDER_POLL_SECONDS,
        id="process_reminders",
    )
    _scheduler.add_job(jobs.prune_tokens, "interval", hours=24, id="prune_tokens")
    _scheduler.add_job(jobs.check_refill_alerts, "interval", hours=24, id="check_refill_alerts")
    _scheduler.add_job(
        jobs.rotate_backups,
        "cron",
        hour=env_int("BACKUP_ROTATE_HOUR", 6),
        minute=0,
        id="rotate_backups",
    )
    _scheduler.add_job(
        jobs.weekly_digest, "cron", day_of_week="mon", hour=8, minute=0, id="weekly_digest"
    )
    _scheduler.add_job(
        jobs.dispatch_web_push,
        "interval",
        seconds=env_int("WEB_PUSH_DISPATCH_SECONDS", 300),
        id="dispatch_web_push",
    )
    _scheduler.add_job(
        jobs.check_ai_providers,
        "interval",
        minutes=env_int("AI_PROVIDER_CHECK_MINUTES", 15),
        id="check_ai_providers",
    )
    _scheduler.add_job(
        jobs.detect_anomalies,
        "interval",
        hours=env_int("ANOMALY_SCAN_HOURS", 6),
        id="detect_anomalies",
    )
    _scheduler.add_job(
        jobs.cleanup_staging,
        "interval",
        minutes=env_int("STAGING_CLEANUP_MINUTES", 60),
        id="cleanup_staging",
    )
    _scheduler.add_job(
        jobs.verify_file_integrity,
        "interval",
        hours=env_int("INTEGRITY_CHECK_HOURS", 24),
        id="verify_file_integrity",
    )
    # Self-gating: ticks hourly, checks the household schedule + last-run.
    _scheduler.add_job(
        jobs.backup_database,
        "interval",
        minutes=env_int("BACKUP_TICK_MINUTES", 60),
        id="backup_database",
    )
    _scheduler.start()
    logger.info("scheduler started (%d jobs)", len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    _release_scheduler_lock()
