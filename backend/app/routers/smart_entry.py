"""Smart entry: quick-add free text → draft entities → confirm persists.

POST /api/v1/smart-entry          {text} → parsed draft (NOT saved)
POST /api/v1/smart-entry/confirm  draft + member_id → persisted entities

The AI only parses text into a JSON draft; member resolution, fuzzy
name/relationship matching and confidence scoring are deterministic code
(ported from v1). Confirm writes real domain rows (medications, labs,
vitals, optionally a health record) with db.add + flush. Text-only by
design — v1's parse endpoint is text-only too, so there is no file-path
deviation.
"""

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_id, get_scoped_member
from app.models import (
    FamilyMember,
    HealthRecord,
    LabFlag,
    LabResult,
    Medication,
    RecordType,
    User,
    VitalMeasurement,
    VitalType,
    normalize_medicine_key,
)
from app.services.ai import router as ai_router
from app.services.ai.extraction import parse_llm_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart-entry", tags=["smart-entry"])

PARSE_SYSTEM = (
    "You parse a short health note into JSON. Use only facts present in "
    "the text — never invent values. Keep the summary to one brief, "
    "professional sentence. Respond with JSON only: "
    '{"member_name": str|null, "record_type": one of doctor_visit|'
    "lab_report|prescription|vaccination|imaging|other|null, "
    '"record_date": "YYYY-MM-DD"|null, "diagnosis": str|null, '
    '"summary": str|null, "provider_name": str|null, '
    '"medications": [{"medicine": str, "dosage": str|null, "timing": '
    'str|null}], "labs": [{"test_name": str, "result": str|null, '
    '"units": str|null, "value_num": number|null, "ref_low_num": '
    'number|null, "ref_high_num": number|null, "flag": '
    'low|normal|high|null}], "vitals": [{"vital_type": one of '
    "blood_pressure|blood_glucose|weight|height|temperature|heart_rate|"
    'spo2|hba1c, "value_num": number, "value_secondary": number|null, '
    '"unit": str|null}], "confidence": high|medium|low}'
)

# v1's colloquial → canonical relationship map, adapted to v2's
# relationship vocabulary (self/spouse/child/parent/sibling/other).
_REL_MAP = {
    "dad": "parent",
    "papa": "parent",
    "appa": "parent",
    "father": "parent",
    "mom": "parent",
    "mama": "parent",
    "amma": "parent",
    "mother": "parent",
    "son": "child",
    "daughter": "child",
    "wife": "spouse",
    "husband": "spouse",
    "spouse": "spouse",
    "brother": "sibling",
    "sister": "sibling",
    "myself": "self",
    "me": "self",
}


class SmartEntryRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000)


class FieldPreview(BaseModel):
    label: str
    value: str


class MemberMatch(BaseModel):
    id: uuid.UUID
    name: str
    matched_by: str  # name | relationship | default


class MedDraft(BaseModel):
    medicine: str = Field(min_length=1, max_length=200)
    dosage: str | None = Field(default=None, max_length=120)
    timing: str | None = Field(default=None, max_length=200)


class LabDraft(BaseModel):
    test_name: str = Field(min_length=1, max_length=200)
    result: str | None = None
    units: str | None = Field(default=None, max_length=50)
    value_num: float | None = Field(default=None, allow_inf_nan=False)
    ref_low_num: float | None = Field(default=None, allow_inf_nan=False)
    ref_high_num: float | None = Field(default=None, allow_inf_nan=False)
    flag: LabFlag | None = None


class VitalDraft(BaseModel):
    vital_type: VitalType
    value_num: float = Field(allow_inf_nan=False)
    value_secondary: float | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = Field(default=None, max_length=20)


class SmartEntryDraft(BaseModel):
    member: MemberMatch | None = None
    record_type: RecordType | None = None
    record_date: str | None = None
    diagnosis: str | None = None
    summary: str | None = None
    provider_name: str | None = None
    medications: list[MedDraft] = []
    labs: list[LabDraft] = []
    vitals: list[VitalDraft] = []
    confidence: str = "medium"
    preview_fields: list[FieldPreview] = []


class SmartEntryConfirm(BaseModel):
    member_id: uuid.UUID
    record_type: RecordType | None = None
    record_date: date | None = None
    diagnosis: str | None = Field(default=None, max_length=5000)
    summary: str | None = Field(default=None, max_length=10000)
    provider_name: str | None = Field(default=None, max_length=200)
    medications: list[MedDraft] = []
    labs: list[LabDraft] = []
    vitals: list[VitalDraft] = []


class SmartEntryConfirmResult(BaseModel):
    record_id: uuid.UUID | None = None
    medication_ids: list[uuid.UUID] = []
    lab_ids: list[uuid.UUID] = []
    vital_ids: list[uuid.UUID] = []


def _match_member(parsed_name: str, members: list[FamilyMember]) -> MemberMatch | None:
    """Fuzzy member resolution: exact name → relationship → partial → default."""
    if not members:
        return None
    raw = (parsed_name or "").lower().strip()
    if raw:
        for m in members:
            if raw == m.name.lower() or raw in m.name.lower().split():
                return MemberMatch(id=m.id, name=m.name, matched_by="name")
        rel = _REL_MAP.get(raw)
        if rel:
            for m in members:
                if m.relationship == rel:
                    return MemberMatch(id=m.id, name=m.name, matched_by="relationship")
        for m in members:
            full = m.name.lower()
            if raw in full or full.startswith(raw):
                return MemberMatch(id=m.id, name=m.name, matched_by="name")
    first = members[0]
    return MemberMatch(id=first.id, name=first.name, matched_by="default")


@router.post("", response_model=SmartEntryDraft)
async def parse_smart_entry(
    body: SmartEntryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SmartEntryDraft:
    """Parse quick-add text into a draft — nothing is persisted."""
    hid = await get_household_id(user, db)
    members = list(await db.scalars(select(FamilyMember).where(FamilyMember.household_id == hid)))
    if not members:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "No family members found. Add a member first."
        )

    plan = await ai_router.plan_for_household(db, hid, local_only=False)
    provider = await ai_router.first_available(plan)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No AI provider available")
    member_context = "; ".join(f"{m.name} ({m.relationship})" for m in members)
    prompt = (
        f"Household members: {member_context}\n\n"
        f"Quick-add note: {body.text}\n\n"
        "Return the JSON draft."
    )
    raw = await provider.complete(prompt, system=PARSE_SYSTEM, max_tokens=800)
    parsed = parse_llm_json(raw)

    member = _match_member(str(parsed.get("member_name") or ""), members)

    record_type = None
    rt_raw = parsed.get("record_type")
    if rt_raw in {t.value for t in RecordType}:
        record_type = RecordType(rt_raw)

    preview_fields: list[FieldPreview] = []
    if record_type:
        preview_fields.append(FieldPreview(label="Type", value=record_type.value))
    if parsed.get("record_date"):
        preview_fields.append(FieldPreview(label="Date", value=str(parsed["record_date"])))
    if parsed.get("diagnosis"):
        preview_fields.append(FieldPreview(label="Diagnosis", value=str(parsed["diagnosis"])))
    meds = parsed.get("medications") or []
    labs = parsed.get("labs") or []
    vitals = parsed.get("vitals") or []
    if meds:
        preview_fields.append(FieldPreview(label="Medicines", value=str(len(meds))))
    if labs:
        preview_fields.append(FieldPreview(label="Lab Tests", value=str(len(labs))))
    if vitals:
        parts = [
            f"{v.get('vital_type')}: {v.get('value_num')}"
            + (f"/{v['value_secondary']}" if v.get("value_secondary") else "")
            for v in vitals
            if isinstance(v, dict)
        ]
        if parts:
            preview_fields.append(FieldPreview(label="Vitals", value=", ".join(parts)))

    confidence = str(parsed.get("confidence") or "medium")
    if member is not None and member.matched_by == "default":
        confidence = "low"

    draft_meds: list[MedDraft] = []
    for m in meds:
        if isinstance(m, dict) and m.get("medicine"):
            draft_meds.append(
                MedDraft(
                    medicine=str(m["medicine"])[:200],
                    dosage=str(m["dosage"]) if m.get("dosage") else None,
                    timing=str(m["timing"]) if m.get("timing") else None,
                )
            )
    draft_labs: list[LabDraft] = []
    for lab in labs:
        if isinstance(lab, dict) and lab.get("test_name"):
            flag = lab.get("flag")
            draft_labs.append(
                LabDraft(
                    test_name=str(lab["test_name"])[:200],
                    result=str(lab["result"]) if lab.get("result") else None,
                    units=str(lab["units"])[:50] if lab.get("units") else None,
                    value_num=_num(lab.get("value_num")),
                    ref_low_num=_num(lab.get("ref_low_num")),
                    ref_high_num=_num(lab.get("ref_high_num")),
                    flag=flag if flag in {f.value for f in LabFlag} else None,
                )
            )
    draft_vitals: list[VitalDraft] = []
    for v in vitals:
        if isinstance(v, dict) and v.get("vital_type") in {t.value for t in VitalType}:
            value = _num(v.get("value_num"))
            if value is None:
                continue
            draft_vitals.append(
                VitalDraft(
                    vital_type=VitalType(v["vital_type"]),
                    value_num=value,
                    value_secondary=_num(v.get("value_secondary")),
                    unit=str(v["unit"])[:20] if v.get("unit") else None,
                )
            )

    return SmartEntryDraft(
        member=member,
        record_type=record_type,
        record_date=str(parsed["record_date"]) if parsed.get("record_date") else None,
        diagnosis=str(parsed["diagnosis"]) if parsed.get("diagnosis") else None,
        summary=str(parsed["summary"]) if parsed.get("summary") else None,
        provider_name=str(parsed["provider_name"]) if parsed.get("provider_name") else None,
        medications=draft_meds,
        labs=draft_labs,
        vitals=draft_vitals,
        confidence=confidence,
        preview_fields=preview_fields,
    )


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.post("/confirm", response_model=SmartEntryConfirmResult)
async def confirm_smart_entry(
    body: SmartEntryConfirm,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SmartEntryConfirmResult:
    """Persist a confirmed draft as real domain rows."""
    member = await get_scoped_member(body.member_id, user, db)
    result = SmartEntryConfirmResult()

    if body.record_type is not None and (body.diagnosis or body.summary or body.provider_name):
        record = HealthRecord(
            member_id=member.id,
            record_type=body.record_type.value,
            record_date=body.record_date or date.today(),
            diagnosis=body.diagnosis,
            summary=body.summary,
            doctor_name=body.provider_name,
        )
        db.add(record)
        await db.flush()
        result.record_id = record.id

    for m in body.medications:
        med = Medication(
            member_id=member.id,
            record_id=result.record_id,
            medicine=m.medicine,
            medicine_key=normalize_medicine_key(m.medicine),
            dosage=m.dosage,
            timing=m.timing,
        )
        db.add(med)
        result.medication_ids.append(med.id)

    for lab_draft in body.labs:
        lab = LabResult(
            member_id=member.id,
            record_id=result.record_id,
            test_name=lab_draft.test_name,
            result=lab_draft.result,
            units=lab_draft.units,
            value_num=lab_draft.value_num,
            ref_low_num=lab_draft.ref_low_num,
            ref_high_num=lab_draft.ref_high_num,
            flag=lab_draft.flag.value if lab_draft.flag else None,
            record_date=body.record_date,
        )
        db.add(lab)
        result.lab_ids.append(lab.id)

    now = datetime.now(UTC).replace(tzinfo=None)
    for v in body.vitals:
        vital = VitalMeasurement(
            member_id=member.id,
            record_id=result.record_id,
            vital_type=v.vital_type.value,
            value_num=v.value_num,
            value_secondary=v.value_secondary,
            unit=v.unit,
            measured_at=now,
        )
        db.add(vital)
        result.vital_ids.append(vital.id)

    await db.flush()
    return result
