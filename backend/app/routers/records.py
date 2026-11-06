"""Health record CRUD, scoped through the member's household."""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_membership, get_scoped_member
from app.models import Attachment, HealthRecord, RecordType, User
from app.schemas.filename_check import (
    FilenameCheckRequest,
    FilenameCheckResponse,
    FilenameMatch,
)
from app.schemas.record import (
    ApplyExtraction,
    RecordCreate,
    RecordMergeRequest,
    RecordResponse,
    RecordUpdate,
)
from app.services.dedup_service import DedupService, compute_content_hash
from app.services.extraction_apply import persist_clinical_data
from app.services.visit_link import apply_visit_autofill, find_linked_visit

router = APIRouter(prefix="/members/{member_id}/records", tags=["records"])

# Confidentiality ceilings (Phase 10, v1's confidentiality semantics):
# which levels each household role may READ. Mutation is already blocked
# for viewers by the role-gate middleware.
_VISIBLE_LEVELS: dict[str, tuple[str, ...]] = {
    "admin": ("household", "caregiver", "private"),
    "member": ("household", "caregiver"),
    "viewer": ("household",),
}


async def _visible_levels(user: User, db: AsyncSession) -> tuple[str, ...]:
    _, role = await get_household_membership(user, db)
    return _VISIBLE_LEVELS.get(role, ("household",))


def _to_response(record: HealthRecord, provider_name: str | None = None) -> RecordResponse:
    from app.schemas.record import AttachmentResponse

    return RecordResponse(
        id=record.id,
        member_id=record.member_id,
        record_type=record.record_type,
        record_date=record.record_date,
        record_time=record.record_time,
        clinical_data=(json.loads(record.clinical_data) if record.clinical_data else None),
        diagnosis=record.diagnosis,
        investigations=record.investigations,
        prescription_text=record.prescription_text,
        summary=record.summary,
        doctor_name=record.doctor_name,
        provider_id=record.provider_id,
        provider_name=provider_name,
        tags=[t for t in (record.tags or "").split(",") if t],
        is_deleted=record.is_deleted,
        confidentiality_level=record.confidentiality_level,
        content_hash=record.content_hash,
        merged_into_id=record.merged_into_id,
        created_at=record.created_at,
        attachments=[AttachmentResponse.model_validate(a) for a in record.attachments],
    )


async def _provider_name(record: HealthRecord, user: User, db: AsyncSession) -> str | None:
    """Directory name for the record's linked provider (household-scoped)."""
    from app.core.deps import get_household_id

    from app.models import Provider

    if record.provider_id is None:
        return None
    household_id = await get_household_id(user, db)
    provider = await db.get(Provider, record.provider_id)
    if provider is None or provider.household_id != household_id:
        return None
    return provider.name


async def _provider_names(records: list[HealthRecord], user: User, db: AsyncSession) -> dict:
    """Batch-resolve provider names for a page of records (one query)."""
    from app.core.deps import get_household_id

    from app.models import Provider

    ids = {r.provider_id for r in records if r.provider_id is not None}
    if not ids:
        return {}
    household_id = await get_household_id(user, db)
    rows = await db.scalars(
        select(Provider).where(Provider.id.in_(ids), Provider.household_id == household_id)
    )
    return {p.id: p.name for p in rows}


async def _validate_provider(
    member_id: uuid.UUID, provider_id: uuid.UUID | None, user: User, db: AsyncSession
) -> None:
    """A record may only reference a provider in the same household."""
    from app.core.deps import get_household_id

    from app.models import Provider

    if provider_id is None:
        return
    household_id = await get_household_id(user, db)
    provider = await db.get(Provider, provider_id)
    if provider is None or provider.household_id != household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")


@router.get("", response_model=list[RecordResponse])
async def list_records(
    member_id: uuid.UUID,
    record_type: RecordType | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecordResponse]:
    await get_scoped_member(member_id, user, db)
    conditions = [HealthRecord.member_id == member_id, HealthRecord.is_deleted.is_(False)]
    levels = await _visible_levels(user, db)
    if len(levels) < 3:  # admin sees everything; others hit the ceiling
        conditions.append(HealthRecord.confidentiality_level.in_(levels))
    if record_type:
        conditions.append(HealthRecord.record_type == record_type.value)
    rows = await db.scalars(
        select(HealthRecord)
        .where(*conditions)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    records = list(rows)
    names = await _provider_names(records, user, db)
    return [_to_response(r, names.get(r.provider_id) if r.provider_id else None) for r in records]


@router.post("", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    member_id: uuid.UUID,
    body: RecordCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecordResponse:
    await get_scoped_member(member_id, user, db)
    await _validate_provider(member_id, body.provider_id, user, db)
    record = HealthRecord(
        member_id=member_id,
        record_type=body.record_type.value,
        record_date=body.record_date,
        record_time=body.record_time,
        clinical_data=json.dumps(body.clinical_data) if body.clinical_data else None,
        diagnosis=body.diagnosis,
        investigations=body.investigations,
        prescription_text=body.prescription_text,
        summary=body.summary,
        doctor_name=body.doctor_name,
        provider_id=body.provider_id,
        tags=",".join(body.tags),
        confidentiality_level=body.confidentiality_level,
        content_hash=(
            compute_content_hash(body.record_type.value, body.record_date, body.clinical_data)
            if body.clinical_data
            else None
        ),
    )
    db.add(record)
    if body.record_type is RecordType.PRESCRIPTION:
        # Prescription integration: a prescription filed near a doctor visit
        # belongs to it — fill empty doctor/provider/diagnosis from the visit.
        visit = await find_linked_visit(db, member_id, body.record_date)
        if visit is not None:
            apply_visit_autofill(record, visit)
    await db.flush()
    await db.refresh(record)
    return _to_response(
        record,
        (await _provider_names([record], user, db)).get(record.provider_id),
    )


async def _get_record_scoped(
    member_id: uuid.UUID, record_id: uuid.UUID, user: User, db: AsyncSession
) -> HealthRecord:
    await get_scoped_member(member_id, user, db)
    record = await db.get(HealthRecord, record_id)
    if record is None or record.member_id != member_id or record.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    # Confidentiality ceiling: 404 (not 403) above the caller's role level —
    # existence itself is information a lower role must not get.
    levels = await _visible_levels(user, db)
    if record.confidentiality_level not in levels:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    return record


# NOTE: literal-path routes ("/duplicates") must register BEFORE
# "/{record_id}" or the UUID converter 422s them.
@router.get("/duplicates")
async def list_duplicates(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Candidate duplicate pairs [{primary_id, duplicate_id, reason, score}]."""
    await get_scoped_member(member_id, user, db)
    return await DedupService(db).find_duplicate_pairs(member_id)


@router.get("/{record_id}", response_model=RecordResponse)
async def get_record(
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecordResponse:
    record = await _get_record_scoped(member_id, record_id, user, db)
    return _to_response(record, await _provider_name(record, user, db))


@router.patch("/{record_id}", response_model=RecordResponse)
async def update_record(
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    body: RecordUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecordResponse:
    record = await _get_record_scoped(member_id, record_id, user, db)
    data = body.model_dump(exclude_unset=True)
    if "clinical_data" in data:
        data["clinical_data"] = json.dumps(data["clinical_data"]) if data["clinical_data"] else None
    if "tags" in data and data["tags"] is not None:
        data["tags"] = ",".join(data["tags"])
    if "provider_id" in data:
        await _validate_provider(member_id, data["provider_id"], user, db)
    for field, value in data.items():
        setattr(record, field, value)
    # Content-addressing: recompute whenever any hash input changed.
    if {"clinical_data", "record_type", "record_date"} & data.keys():
        if record.clinical_data:
            record.content_hash = compute_content_hash(
                record.record_type, record.record_date, json.loads(record.clinical_data)
            )
        else:
            record.content_hash = None
    await db.flush()
    await db.refresh(record)
    return _to_response(record, await _provider_name(record, user, db))


@router.post("/{record_id}/apply-extraction")
async def apply_extraction_to_record(
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    body: ApplyExtraction,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persist an extraction result onto a record.

    Saves the structured payload as the record's clinical_data (the
    "structured data saved alongside the original"), creates LabResult /
    VitalMeasurement rows for its labs and vitals, and fills summary /
    diagnosis / record_date / doctor_name when provided.

    Merges per-key rather than replacing: a record built from several
    documents (Rx then lab report) accumulates — an empty section in the
    new payload never erases data a previous document contributed.
    """
    record = await _get_record_scoped(member_id, record_id, user, db)
    if body.summary is not None:
        record.summary = body.summary
    if body.diagnosis is not None:
        record.diagnosis = body.diagnosis
    if body.record_date is not None:
        record.record_date = body.record_date
    if body.doctor_name is not None:
        record.doctor_name = body.doctor_name
    existing: dict = {}
    if record.clinical_data:
        try:
            existing = json.loads(record.clinical_data)
        except ValueError:
            existing = {}
    merged = dict(existing)
    for key, value in body.clinical_data.items():
        # Empty sections don't clobber what earlier documents contributed.
        if value is None or value == [] or value == "":
            continue
        merged[key] = value
    record.clinical_data = json.dumps(merged)
    labs_created, vitals_created = await persist_clinical_data(
        db, member_id, record.id, record.record_date, body.clinical_data
    )
    # Content-addressing: the clinical payload is a hash input.
    record.content_hash = compute_content_hash(
        record.record_type, record.record_date, body.clinical_data
    )
    await db.flush()
    return {
        "record_id": str(record.id),
        "labs_created": labs_created,
        "vitals_created": vitals_created,
    }


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    record = await _get_record_scoped(member_id, record_id, user, db)
    record.is_deleted = True  # soft delete — keeps timeline history auditable
    await db.flush()


@router.post("/{record_id}/merge", response_model=RecordResponse)
async def merge_record(
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    body: RecordMergeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecordResponse:
    """Merge this record (the duplicate) into ``duplicate_of_id``.

    Idempotent: re-merging into the same primary returns the primary
    unchanged; merging into a *different* primary is a 409.
    """
    # NOTE: not _get_record_scoped — an already-merged duplicate must still
    # reach DedupService.merge_duplicate so the re-merge is a no-op rather
    # than a 404 (idempotency invariant).
    await get_scoped_member(member_id, user, db)
    record = await db.get(HealthRecord, record_id)
    if (
        record is None
        or record.member_id != member_id
        or record.confidentiality_level not in await _visible_levels(user, db)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    primary = await db.get(HealthRecord, body.duplicate_of_id)
    if (
        primary is None
        or primary.member_id != member_id
        or primary.confidentiality_level not in await _visible_levels(user, db)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    try:
        merged = await DedupService(db).merge_duplicate(member_id, record.id, body.duplicate_of_id)
    except ValueError as exc:
        message = str(exc)
        if "itself" in message:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, message) from exc
        if "already merged into another" in message:
            raise HTTPException(status.HTTP_409_CONFLICT, message) from exc
        raise HTTPException(status.HTTP_404_NOT_FOUND, message) from exc
    return _to_response(merged, await _provider_name(merged, user, db))


@router.get("/count/all")
async def count_records(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await get_scoped_member(member_id, user, db)
    total = await db.scalar(
        select(func.count())
        .select_from(HealthRecord)
        .where(HealthRecord.member_id == member_id, HealthRecord.is_deleted.is_(False))
    )
    return {"count": total or 0}


@router.post("/check-filenames")
async def check_filenames(
    member_id: uuid.UUID,
    body: FilenameCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FilenameCheckResponse:
    """Warn before uploading files this member already has.

    original_name is encrypted at rest, so matching happens in Python over
    the member's decrypted attachment names (fine at family scale).
    """
    await get_scoped_member(member_id, user, db)
    wanted = {name.strip().lower() for name in body.filenames if name.strip()}
    rows = await db.execute(
        select(HealthRecord, Attachment)
        .join(Attachment, Attachment.record_id == HealthRecord.id)
        .where(HealthRecord.member_id == member_id, HealthRecord.is_deleted.is_(False))
    )
    matches = [
        FilenameMatch(
            record_id=str(record.id),
            record_type=record.record_type,
            record_date=record.record_date.isoformat(),
            filename=attachment.original_name,
        )
        for record, attachment in rows
        if attachment.original_name.strip().lower() in wanted
    ]
    return FilenameCheckResponse(matches=matches)
