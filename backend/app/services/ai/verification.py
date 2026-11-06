"""Second-model verification of extractions + claim-level audit agent.

Extraction verification runs as a background task after extraction: a
second provider (different name when possible) is asked to audit the
extraction JSON against the document text.

The audit agent runs the same way for reports, health Q&A and chat: it
rebuilds the member's evidence index on its own session, verifies the
narrative's claims against the record, and — only with the member's
explicit opt-in — checks eligible claims with SearXNG. The verdict and
the claim table land in the verifications row; the client polls.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

import json_repair
from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import FamilyMember, Verification
from app.models.verification import VerificationStatus

logger = logging.getLogger(__name__)

VERIFY_SYSTEM = (
    "You are a meticulous medical-records auditor. Compare the extraction "
    "against the source document and report only real discrepancies."
)

# Strong refs for fire-and-forget tasks: the loop keeps only weak refs,
# so an untracked task can be garbage-collected mid-run.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def build_verify_prompt(document_text: str, extraction: dict) -> str:
    return (
        "Source document:\n---\n"
        f"{document_text}\n---\n\n"
        "Extraction to audit (JSON):\n"
        f"{json.dumps(extraction, ensure_ascii=False)}\n\n"
        'Respond with ONE JSON object: {"verdict": "pass" | "flag", '
        '"notes": "semicolon-separated list of discrepancies, or empty string '
        'if none"}. Flag only facts that contradict the document or invented '
        "values; not stylistic differences."
    )


def parse_verdict(raw: str) -> tuple[VerificationStatus, str | None]:
    # json_repair, not json.loads: local models love markdown fences and
    # leading prose around an otherwise valid verdict object.
    try:
        data = json_repair.loads((raw or "").strip())
    except Exception:
        return VerificationStatus.FAILED, "verifier returned unparseable output"
    if not isinstance(data, dict):
        return VerificationStatus.FAILED, "verifier returned unexpected output"
    verdict = str(data.get("verdict", "")).lower()
    notes = data.get("notes") or None
    if verdict == "pass":
        return VerificationStatus.PASSED, notes
    if verdict == "flag":
        return VerificationStatus.FLAGGED, str(notes) if notes else "flagged without notes"
    return VerificationStatus.FAILED, "verifier returned unknown verdict"


async def schedule_verification(
    db,
    member_id: uuid.UUID,
    subject_type: str,
    document_text: str,
    payload: dict,
    verifier,  # AIProvider
    subject_id: uuid.UUID | None = None,
    commit: bool = True,
) -> uuid.UUID:
    """Create the pending verification row and fire the background audit on
    its OWN session — the request session closes with the response.

    commit=True commits the row immediately (request handlers). Streaming
    generators pass commit=False to flush, so the row lands in the same
    transaction as the insight/message they persist alongside it."""
    row = Verification(
        member_id=member_id,
        subject_type=subject_type,
        subject_id=subject_id,
        status=VerificationStatus.PENDING.value,
    )
    db.add(row)
    if commit:
        await db.commit()
    else:
        await db.flush()
    task = asyncio.create_task(run_verification(row.id, document_text, payload, verifier))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return row.id


async def run_verification(
    verification_id: uuid.UUID,
    document_text: str,
    extraction: dict,
    verifier,  # AIProvider | list[AIProvider]
) -> None:
    """Background audit on its own session (the request session is gone).

    ``verifier`` may be a single provider or an ordered candidate list —
    a candidate that errors (dead key, down Ollama) is marked unhealthy
    and the next one takes the audit; FAILED settles only after all fail."""
    from app.services.ai.router import mark_unhealthy

    candidates = verifier if isinstance(verifier, list) else [verifier]
    status: VerificationStatus | None = None
    notes: str | None = None
    verifier_name: str | None = None
    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            raw = await candidate.complete(
                build_verify_prompt(document_text, extraction),
                system=VERIFY_SYSTEM,
                max_tokens=1000,
            )
            status, notes = parse_verdict(raw)
            verifier_name = getattr(candidate, "name", None)
            if status is not VerificationStatus.FAILED:
                break
            # Unparseable/unknown verdict: leave health alone (a chatty
            # local model isn't down) but let the next candidate try.
        except Exception as exc:  # noqa: BLE001 — dead key must not strand the row
            last_exc = exc
            mark_unhealthy(getattr(candidate, "name", ""))
    if status is None:
        # A dead key / timeout / down Ollama must not strand the row as
        # PENDING forever — the client would poll it eternally.
        status = VerificationStatus.FAILED
        notes = f"verifier failed: {last_exc}"
    async with SessionLocal() as db:
        row = await db.get(Verification, verification_id)
        if row is None:
            return
        row.status = status.value
        row.notes = notes
        row.verifier_name = verifier_name
        row.completed_at = datetime.now(UTC)
        await db.commit()


def pick_verifiers(plan: list, used_name: str) -> list:
    """Ordered verifier candidates: every other provider first (an
    independent cross-check beats a self-check), then the provider that
    produced the output. The run_* functions fail over down this list,
    so a dead verifier key (401, placeholder credential) no longer
    sinks the whole verification — the next candidate takes it."""
    seen: set[str] = set()
    candidates: list = []
    for provider in plan:
        name = getattr(provider, "name", "")
        if name in seen:
            continue
        seen.add(name)
        candidates.append(provider)
    candidates.sort(key=lambda p: getattr(p, "name", "") == used_name)
    return candidates


def pick_verifier(plan: list, used_name: str):
    """First verifier candidate (different provider than the one that did
    the work; same-name self-check only when it's all there is)."""
    candidates = pick_verifiers(plan, used_name)
    return candidates[0] if candidates else None


async def schedule_audit(
    db,
    member_id: uuid.UUID,
    subject_type: str,
    narrative: str,
    verifier,  # AIProvider
    *,
    kind: str | None = None,
    subject_id: uuid.UUID | None = None,
    commit: bool = True,
) -> uuid.UUID:
    """Create the pending verification row and fire the audit in the
    background on its own session.

    Streaming generators pass ``commit=False`` so the row lands in the same
    transaction as the insight/message they persist alongside it."""
    row = Verification(
        member_id=member_id,
        subject_type=subject_type,
        subject_id=subject_id,
        status=VerificationStatus.PENDING.value,
    )
    db.add(row)
    if commit:
        await db.commit()
    else:
        await db.flush()
    task = asyncio.create_task(
        run_audit(row.id, member_id, subject_type, narrative, verifier, kind=kind)
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return row.id


async def run_audit(
    verification_id: uuid.UUID,
    member_id: uuid.UUID,
    subject_type: str,
    narrative: str,
    verifier,  # AIProvider | list[AIProvider]
    *,
    kind: str | None = None,
) -> None:
    """Background audit: history index → claims → optional web → verdict.

    ``verifier`` may be a single provider or an ordered candidate list;
    a candidate that errors is marked unhealthy and the next one re-runs
    the audit. Never raises into the caller; FAILED settles only after
    every candidate has failed, so the client stops polling either way."""
    from app.services.ai.router import mark_unhealthy

    async def _row(db):
        # The streaming caller flushes the row and commits right after
        # scheduling; a fast audit can reach this point first.
        for _ in range(20):
            row = await db.get(Verification, verification_id)
            if row is not None:
                return row
            await db.rollback()
            await asyncio.sleep(0.1)
        return None

    async def _audit_once(candidate) -> None:
        from app.services.ai import web_search
        from app.services.ai.agents import auditor, history

        async with SessionLocal() as db:
            member = await db.get(FamilyMember, member_id)
            context = await history.build_audit_context(db, member_id)

            draft = await auditor.extract_claims(
                narrative, context, candidate, kind=kind
            )

            web_by_claim = {}
            if member is not None and web_search.web_allowed(member) and draft.claims:
                checks = await auditor.run_web_checks(
                    draft,
                    context=context,
                    db=db,
                    household_id=member.household_id,
                )
                web_by_claim = await auditor.adjudicate_web(draft, checks, candidate)

            interactions = await auditor.check_interactions(db, member_id, candidate)
            report = auditor.assemble(
                draft,
                context,
                web_by_claim=web_by_claim,
                interactions=interactions,
            )

            row = await _row(db)
            if row is None:
                return
            row.status = report.overall
            row.notes = report.summary
            row.audit_json = report.model_dump_json()
            row.verifier_name = getattr(candidate, "name", None)
            row.completed_at = datetime.now(UTC)
            await db.commit()

    candidates = verifier if isinstance(verifier, list) else [verifier]
    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            await _audit_once(candidate)
            return
        except Exception as exc:  # noqa: BLE001 — a failed audit must settle
            last_exc = exc
            logger.warning(
                "Audit candidate %s failed for %s",
                getattr(candidate, "name", "?"),
                subject_type,
                exc_info=True,
            )
            mark_unhealthy(getattr(candidate, "name", ""))
    async with SessionLocal() as db:
        row = await _row(db)
        if row is None:
            return
        row.status = VerificationStatus.FAILED.value
        row.notes = f"audit failed: {last_exc}"
        row.verifier_name = getattr(candidates[-1], "name", None) if candidates else None
        row.completed_at = datetime.now(UTC)
        await db.commit()


async def settle_orphaned_verifications() -> int:
    """Mark PENDING rows failed at startup — their background tasks died
    with the previous process (restart, crash, desktop relaunch), so the
    client would poll them forever. Returns the number settled."""
    async with SessionLocal() as db:
        result = await db.execute(
            update(Verification)
            .where(Verification.status == VerificationStatus.PENDING.value)
            .values(
                status=VerificationStatus.FAILED.value,
                notes="aborted: server restarted before the audit finished",
                completed_at=datetime.now(UTC),
            )
        )
        await db.commit()
        return result.rowcount or 0
