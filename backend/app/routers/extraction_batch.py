"""Batch extraction SSE endpoint (Phase 10).

POST /api/v1/extract/batch/stream — multipart with several files → an SSE
stream that fans out over the files SEQUENTIALLY, reusing the single-file
extraction plumbing (same provider plan, same progress callbacks, same
heartbeat pattern via ``sse_response``). Each file produces its own event
pair (``file_start`` then ``complete``/``error``) and its own commit, so a
client reading the stream incrementally — including a chunked-reassembly
client that lost the connection midway — keeps every record that already
completed. Each created record is tagged with a ``content_hash`` over its
canonical clinical payload so the batch output feeds the dedup/merge flow.
"""

import asyncio
import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, get_scoped_member
from app.core.sse import sse_response
from app.models import HealthRecord, RecordType, User
from app.services.visit_link import apply_visit_autofill, find_linked_visit
from app.services.ai import extraction as extraction_svc
from app.services.ai.verification import pick_verifiers, schedule_verification
from app.services.dedup_service import compute_content_hash
from app.routers.extraction import (
    _document_text,
    _read_upload,
    _resolve_provider,
    _spawn,
)

router = APIRouter(prefix="/extract", tags=["extraction"])
logger = logging.getLogger(__name__)

MAX_BATCH_FILES = 20


def _progress_callback(queue: asyncio.Queue, filename: str):
    """Stage/heartbeat events tagged with the file they belong to."""

    def progress(stage: str, message: str) -> None:
        queue.put_nowait({"stage": stage, "message": message, "filename": filename})

    return progress


def _record_date_from(clinical_data: dict) -> date:
    raw = clinical_data.get("record_date")
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    return date.today()


@router.post("/batch/stream")
async def extract_batch_stream(
    member_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract several documents in one SSE stream, one result per file."""
    await get_scoped_member(member_id, user, db)
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Batch limited to {MAX_BATCH_FILES} files",
        )
    _, plan, provider = await _resolve_provider(member_id, user, db)

    payloads: list[UploadFile] = files
    total = len(payloads)

    async def source():
        # Queue bridge: the sync progress callback emits while awaits run.
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def run():
            # Own session: the request session closes with the response, so
            # continuing work after a client disconnect must not borrow it.
            async with SessionLocal() as task_db:
                for index, file in enumerate(payloads):
                    filename = file.filename or f"file-{index + 1}"
                    queue.put_nowait(
                        {
                            "stage": "file_start",
                            "filename": filename,
                            "index": index,
                            "total": total,
                        }
                    )
                    try:
                        # Read + validate INSIDE the stream: an unsupported or
                        # oversized file becomes a per-file error event instead
                        # of failing the whole batch request.
                        data, mime = await _read_upload(file)
                        result = await extraction_svc.run_extraction(
                            data, mime, provider, _progress_callback(queue, filename)
                        )
                        clinical = result.clinical_data or {}
                        record_date = _record_date_from(clinical)
                        content_hash = compute_content_hash(
                            RecordType.OTHER.value, record_date, clinical
                        )
                        # Extracted meds make this a prescription; link it to a
                        # nearby doctor visit the same way manual filing does.
                        record_type = (
                            RecordType.PRESCRIPTION if clinical.get("medications") else RecordType.OTHER
                        )
                        record = HealthRecord(
                            member_id=member_id,
                            record_type=record_type.value,
                            record_date=record_date,
                            clinical_data=json.dumps(clinical),
                            summary=result.summary,
                            diagnosis=clinical.get("diagnosis"),
                            doctor_name=clinical.get("doctor_name"),
                            content_hash=content_hash,
                        )
                        task_db.add(record)
                        if record_type is RecordType.PRESCRIPTION:
                            visit = await find_linked_visit(task_db, member_id, record_date)
                            if visit is not None:
                                apply_visit_autofill(record, visit)
                        await task_db.flush()

                        verification_id = None
                        if get_settings().AI_VERIFICATION_ENABLED:
                            verifier = pick_verifiers(plan, provider.name)
                            if verifier:
                                queue.put_nowait(
                                    {
                                        "stage": "verifying",
                                        "message": "second model reviewing",
                                        "filename": filename,
                                    }
                                )
                                verification_id = await schedule_verification(
                                    task_db,
                                    member_id,
                                    "extraction",
                                    _document_text(data, mime),
                                    result.clinical_data,
                                    verifier,
                                )
                        await task_db.commit()  # per-file commit: partial batches survive
                        queue.put_nowait(
                            {
                                "stage": "complete",
                                "filename": filename,
                                "index": index,
                                "total": total,
                                "result": {
                                    "record_id": str(record.id),
                                    "content_hash": content_hash,
                                    "clinical_data": clinical,
                                    "summary": result.summary,
                                    "provider_used": result.provider_used,
                                    "verification_id": str(verification_id)
                                    if verification_id
                                    else None,
                                },
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 — one bad file must not kill the batch
                        await task_db.rollback()
                        logger.warning("Batch extraction failed for %s: %s", filename, exc)
                        queue.put_nowait(
                            {
                                "stage": "error",
                                "filename": filename,
                                "index": index,
                                "total": total,
                                "message": str(exc),
                            }
                        )
            queue.put_nowait(None)

        task = _spawn(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    # Sentinel from run(): batch finished — end the stream
                    # instead of blocking on get() forever.
                    return
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            # Client went away — stop the batch instead of committing a
            # record per remaining file into a closed connection.
            task.cancel()
            raise

    return sse_response(source())
