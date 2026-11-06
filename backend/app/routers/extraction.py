"""AI document extraction endpoints (blocking + SSE)."""

import asyncio
import uuid

import fitz
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from PIL import UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, get_scoped_member
from app.core.sse import sse_response
from app.models import HealthRecord, User
from app.services.ai import extraction as extraction_svc
from app.services.ai import router as ai_router
from app.services.ai.base import ExtractionResult
from app.services.ai.verification import pick_verifiers, schedule_verification
from app.services import health_alert_service
from app.core.storage import ALLOWED_MIME, _magic_ok, validate_size

router = APIRouter(prefix="/members/{member_id}/records", tags=["extraction"])

# Strong refs for fire-and-forget tasks: the loop keeps only weak refs, so
# an untracked task can be garbage-collected mid-run (CPython pitfall).
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read()
    validate_size(data)
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported type: {mime}")
    if not _magic_ok(data, mime):
        # The client-declared type passed; the bytes say otherwise.
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File content does not match its type"
        )
    return data, mime


def _document_text(data: bytes, mime: str) -> str:
    """Best-effort plain text for verification (empty for scans/images)."""
    if mime != "application/pdf":
        return ""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(doc[n].get_text() for n in range(doc.page_count))
    except fitz.FileDataError:
        return ""


async def _resolve_provider(member_id: uuid.UUID, user: User, db: AsyncSession):
    """Scoped member → consent-aware provider plan → first available."""
    member = await get_scoped_member(member_id, user, db)
    plan = await ai_router.plan_for_household(
        db, member.household_id, local_only=not member.cloud_ai_consent
    )
    provider = await ai_router.first_available(plan)
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No AI provider available (is Ollama running, or a cloud key set?)",
        )
    return member, plan, provider


async def _raise_lab_alerts(
    db: AsyncSession, member_id: uuid.UUID, result: ExtractionResult
) -> int:
    """Health-alert hook: flagged labs (low/high) become HealthAlert rows."""
    alerts = await health_alert_service.create_alerts_for_labs(
        db, member_id, None, result.clinical_data.get("labs") or []
    )
    return len(alerts)


async def _record_for_provenance(
    member_id: uuid.UUID, record_id: uuid.UUID | None, db: AsyncSession
) -> HealthRecord | None:
    """The (scoped, live) record an extraction is attached to, or None."""
    if record_id is None:
        return None
    record = await db.get(HealthRecord, record_id)
    if record is None or record.member_id != member_id or record.is_deleted:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown record_id")
    return record


@router.post("/extract")
async def extract_document(
    member_id: uuid.UUID,
    file: UploadFile,
    record_id: uuid.UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data, mime = await _read_upload(file)
    _, plan, provider = await _resolve_provider(member_id, user, db)
    await _record_for_provenance(member_id, record_id, db)
    try:
        result = await extraction_svc.run_extraction(data, mime, provider)
    except (UnidentifiedImageError, fitz.FileDataError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not decode the file as its claimed type"
        ) from exc
    alerts_created = await _raise_lab_alerts(db, member_id, result)

    verification_id = None
    if get_settings().AI_VERIFICATION_ENABLED:
        verifier = pick_verifiers(plan, provider.name)
        if verifier:
            verification_id = await schedule_verification(
                db,
                member_id,
                "extraction",
                _document_text(data, mime),
                result.clinical_data,
                verifier,
                subject_id=record_id,
            )

    return {
        "clinical_data": result.clinical_data,
        "summary": result.summary,
        "provider_used": result.provider_used,
        "verification_id": str(verification_id) if verification_id else None,
        "health_alerts_created": alerts_created,
    }


@router.post("/extract/stream")
async def extract_document_stream(
    member_id: uuid.UUID,
    file: UploadFile,
    record_id: uuid.UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data, mime = await _read_upload(file)
    _, plan, provider = await _resolve_provider(member_id, user, db)
    await _record_for_provenance(member_id, record_id, db)

    async def source():
        # Queue bridge: the sync progress callback emits while awaits run.
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def run():
            # Own session: the request session closes with the response — a
            # client disconnecting mid-stream would tear the session out from
            # under this task if it borrowed the request's.
            try:
                async with SessionLocal() as task_db:
                    result = await extraction_svc.run_extraction(
                        data, mime, provider, _queue_progress(queue)
                    )
                    alerts_created = await _raise_lab_alerts(task_db, member_id, result)
                    if alerts_created:
                        queue.put_nowait(
                            {
                                "stage": "alerts",
                                "message": f"{alerts_created} lab alert(s) created",
                            }
                        )
                    verification_id = None
                    if get_settings().AI_VERIFICATION_ENABLED:
                        verifier = pick_verifiers(plan, provider.name)
                        if verifier:
                            queue.put_nowait(
                                {"stage": "verifying", "message": "second model reviewing"}
                            )
                            verification_id = await schedule_verification(
                                task_db,
                                member_id,
                                "extraction",
                                _document_text(data, mime),
                                result.clinical_data,
                                verifier,
                                subject_id=record_id,
                            )
                    await task_db.commit()
                    queue.put_nowait(
                        {
                            "stage": "complete",
                            "result": {
                                "clinical_data": result.clinical_data,
                                "summary": result.summary,
                                "provider_used": result.provider_used,
                                "verification_id": str(verification_id)
                                if verification_id
                                else None,
                                "health_alerts_created": alerts_created,
                            },
                        }
                    )
            except Exception as exc:
                queue.put_nowait({"stage": "error", "message": str(exc)})
            finally:
                queue.put_nowait(None)

        task = _spawn(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    # Sentinel from run()'s finally: work is done — end the
                    # stream instead of blocking on get() forever (a browser
                    # hides this by disconnecting; a test client hangs).
                    return
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            # Client went away — stop the work instead of extracting into a
            # closed connection.
            task.cancel()
            raise

    return sse_response(source())


def _queue_progress(queue: asyncio.Queue):
    def progress(stage: str, message: str) -> None:
        queue.put_nowait({"stage": stage, "message": message})

    return progress
