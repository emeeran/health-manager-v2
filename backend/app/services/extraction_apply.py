"""Persist extraction payloads as domain rows alongside the record.

The structured data an AI extraction finds (labs, vitals) becomes real
LabResult / VitalMeasurement rows linked to the HealthRecord, so trends,
alerts, and the record page all read the same data. Medications are
deliberately NOT auto-created here — the UI prompts the user to update
their currently-taking list instead.
"""

import json
import re
import uuid
from datetime import datetime, time, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LabResult, VitalMeasurement

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
# Reference ranges like "70-100", "70 to 100", "4.0–10.0".
_REF_RANGE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(-?\d+(?:\.\d+)?)")


def _float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not _NUM_RE.match(text):
        return None
    return float(text)


def _parse_labs(entries: list, member_id, record_id, record_date) -> list[LabResult]:
    rows: list[LabResult] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        ref_low = ref_high = None
        match = _REF_RANGE_RE.search(str(entry.get("reference") or ""))
        if match:
            ref_low, ref_high = float(match.group(1)), float(match.group(2))
        rows.append(
            LabResult(
                member_id=member_id,
                record_id=record_id,
                test_name=str(entry["name"]),
                result=(str(entry["result"]) if entry.get("result") is not None else None),
                units=entry.get("units"),
                value_num=_float(entry.get("result")),
                ref_value=entry.get("reference"),
                ref_low_num=ref_low,
                ref_high_num=ref_high,
                flag=entry.get("flag"),
                record_date=record_date,
            )
        )
    return rows


def _parse_vitals(entries: list, member_id, record_id, measured_at) -> list[VitalMeasurement]:
    rows: list[VitalMeasurement] = []
    for entry in entries:
        value = _float(entry.get("value")) if isinstance(entry, dict) else None
        if not isinstance(entry, dict) or not entry.get("type") or value is None:
            continue
        rows.append(
            VitalMeasurement(
                member_id=member_id,
                record_id=record_id,
                vital_type=str(entry["type"]),
                value_num=value,
                value_secondary=_float(entry.get("value_secondary")),
                unit=entry.get("unit"),
                measured_at=measured_at,
            )
        )
    return rows


async def persist_clinical_data(
    db: AsyncSession,
    member_id: uuid.UUID,
    record_id: uuid.UUID,
    record_date,
    clinical_data: str | dict | None,
) -> tuple[int, int]:
    """Create LabResult / VitalMeasurement rows from a clinical_data payload.

    Returns (labs_created, vitals_created). Idempotent: a row matching an
    existing one for this record (same test/type and date) is skipped, so
    a retried apply — response lost after the server committed — doesn't
    duplicate rows. Rows added by hand or by another document are kept.
    """
    if isinstance(clinical_data, str):
        data = json.loads(clinical_data) if clinical_data else {}
    else:
        data = clinical_data or {}
    fallback = datetime.now(UTC).replace(tzinfo=None)
    measured_at = datetime.combine(record_date, time.min) if record_date else fallback
    existing_labs = set(
        await db.scalars(
            select(LabResult.test_name).where(
                LabResult.record_id == record_id,
                LabResult.record_date == record_date,
            )
        )
    )
    existing_vitals = set(
        await db.scalars(
            select(VitalMeasurement.vital_type).where(
                VitalMeasurement.record_id == record_id,
                VitalMeasurement.measured_at == measured_at,
            )
        )
    )
    labs = [
        row
        for row in _parse_labs(data.get("labs") or [], member_id, record_id, record_date)
        if row.test_name not in existing_labs
    ]
    vitals = [
        row
        for row in _parse_vitals(data.get("vitals") or [], member_id, record_id, measured_at)
        if row.vital_type not in existing_vitals
    ]
    for row in labs:
        db.add(row)
    for vital_row in vitals:
        db.add(vital_row)
    return len(labs), len(vitals)
