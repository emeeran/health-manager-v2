"""Voice memos — audio → transcript for the smart-entry box.

POST /members/{id}/voice-memos          multipart audio → {text, duration_s}
GET  /voice-memos/capabilities          availability probe (no 501 here)

Nothing is persisted: transcription is a transform, not a record. 501 (not
500) when faster-whisper is absent — the feature is intentionally
unavailable, and clients can hide the mic button off the capability probe.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.services.voice_service import (
    INSTALL_HINT,
    model_size,
    transcribe,
    whisper_available,
)

router = APIRouter(tags=["voice-memos"])
logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB ≈ 30+ minutes of webm/opus


@router.get("/voice-memos/capabilities")
async def voice_capabilities(user: User = Depends(get_current_user)) -> dict:
    """Whether local transcription is available (mic button visibility)."""
    available = whisper_available()
    return {"available": available, "model_size": model_size() if available else None}


@router.post("/members/{member_id}/voice-memos", response_model=None)
async def create_voice_memo(
    member_id: uuid.UUID,
    audio: UploadFile,
    language: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict | JSONResponse:
    """Transcribe a voice memo; the audio is never stored."""
    await get_scoped_member(member_id, user, db)
    if not whisper_available():
        # {"detail", "install_hint"} at the top level — HTTPException only
        # supports `detail`, and self-hosters need the one-liner fix too.
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={
                "detail": (
                    "Voice memos are disabled: install faster-whisper to enable local transcription"
                ),
                "install_hint": INSTALL_HINT,
            },
        )
    if audio.content_type and not audio.content_type.startswith("audio/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Audio file required")
    data = await audio.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio too large (25 MB limit)"
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty audio upload")
    try:
        # CPU-heavy (the model decodes audio on this machine) — keep the
        # event loop free for other requests.
        text, duration_s = await asyncio.to_thread(transcribe, data, language)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc))
    except Exception as exc:
        logger.warning("Transcription failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcription failed — try again")
    if not text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "No speech detected in the recording"
        )
    return {"text": text, "duration_s": duration_s}
