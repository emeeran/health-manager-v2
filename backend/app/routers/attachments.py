"""Attachment upload/download against the content-addressable store."""

import asyncio
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import Response as FastResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.core.storage import read_plaintext, save_upload
from app.core.thumbnails import get_or_create_thumbnail, render_pdf_page
from app.models import Attachment, HealthRecord, User
from app.routers.records import _get_record_scoped
from app.schemas.record import AttachmentResponse

router = APIRouter(tags=["attachments"])

# A request reads every file fully into memory — one oversized batch
# shouldn't be able to OOM the process (the batch extractor caps at 20 too).
MAX_ATTACHMENT_FILES = 20


def _content_disposition(filename: str) -> str:
    """ASCII fallback + RFC 5987 form; a quote or control char in the
    stored name must not break the header (or 500 the download)."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    ascii_name = "".join(c if c.isprintable() else "_" for c in ascii_name)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.post(
    "/members/{member_id}/records/{record_id}/attachments",
    response_model=list[AttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachments(
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    files: list[UploadFile],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AttachmentResponse]:
    record = await _get_record_scoped(member_id, record_id, user, db)
    if len(files) > MAX_ATTACHMENT_FILES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"At most {MAX_ATTACHMENT_FILES} files per request",
        )
    created: list[Attachment] = []
    for upload in files:
        stored = await save_upload(upload)
        existing = await db.scalar(
            select(Attachment).where(
                Attachment.record_id == record.id,
                Attachment.content_hash == stored.content_hash,
            )
        )
        if existing:  # same file already attached to this record
            created.append(existing)
            continue
        attachment = Attachment(
            record_id=record.id,
            file_path=stored.rel_path,
            content_hash=stored.content_hash,
            file_size=stored.size,
            mime=stored.mime,
            original_name=upload.filename or f"file{stored.ext}",
        )
        db.add(attachment)
        created.append(attachment)
    await db.flush()
    for attachment in created:
        await db.refresh(attachment)
    return [AttachmentResponse.model_validate(a) for a in created]


async def _get_attachment_scoped(
    attachment_id: uuid.UUID, user: User, db: AsyncSession
) -> Attachment:
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    # Scope through the attachment's record's member.
    record = await db.get(HealthRecord, attachment.record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    await get_scoped_member(record.member_id, user, db)
    return attachment


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FastResponse:
    attachment = await _get_attachment_scoped(attachment_id, user, db)
    data = read_plaintext(attachment.file_path)
    return Response(
        content=data,
        media_type=attachment.mime,
        headers={"Content-Disposition": _content_disposition(attachment.original_name)},
    )


@router.get("/attachments/{attachment_id}/preview")
async def preview_attachment(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FastResponse:
    attachment = await _get_attachment_scoped(attachment_id, user, db)
    data = read_plaintext(attachment.file_path)
    return Response(
        content=data,
        media_type=attachment.mime,
        headers={"Content-Disposition": "inline"},
    )


@router.get("/attachments/{attachment_id}/thumbnail")
async def attachment_thumbnail(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FastResponse:
    attachment = await _get_attachment_scoped(attachment_id, user, db)
    thumb = await get_or_create_thumbnail(attachment.content_hash, attachment.file_path)
    return Response(
        content=thumb,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/attachments/{attachment_id}/pages/{page_number}")
async def attachment_page(
    attachment_id: uuid.UUID,
    page_number: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FastResponse:
    attachment = await _get_attachment_scoped(attachment_id, user, db)
    if attachment.mime != "application/pdf":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Page rendering is only available for PDFs"
        )
    data = read_plaintext(attachment.file_path)
    png = await asyncio.to_thread(render_pdf_page, data, page_number)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": "inline"},
    )
