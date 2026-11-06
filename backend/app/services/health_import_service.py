"""Apple Health Export.xml ingest (Phase 10, ported from v1).

Apple's export is one enormous ``Export.xml`` (hundreds of MB of
``<Record>`` elements) — parsed with ``iterparse`` and cleared per
element, so memory stays flat regardless of file size. Records aggregate
to ONE VitalMeasurement row per (member, vital type, day): a year of
heart-rate samples becomes 365 rows, not 50,000. Re-uploads are
IDEMPOTENT — an existing (member, type, day, source="health_import") row
updates in place, which is also the (type, date, value) dedupe.

Blood pressure arrives as separate systolic/diastolic identifiers; both
aggregate to the same day and pair into a single BP row
(value_num=systolic, value_secondary=diastolic).

Type mapping (identifier suffix → VitalType/unit):
  HeartRate→heart_rate/bpm · OxygenSaturation→spo2/% · BloodGlucose→mg/dL
  BodyMass→weight/kg · Height→height/cm · BodyTemperature→temperature/°C
  BloodPressureSystolic/Diastolic→blood_pressure/mmHg

Deviation from v1: RespiratoryRate has no v2 VitalType member and is
counted under skipped_types instead of imported.
"""

import io
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, time, UTC
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VitalMeasurement, VitalType

logger = logging.getLogger(__name__)

MAX_EXPORT_BYTES = 300 * 1024 * 1024  # Apple exports reach hundreds of MB

_TYPE_MAP: dict[str, tuple[VitalType, str]] = {
    "HKQuantityTypeIdentifierHeartRate": (VitalType.HEART_RATE, "bpm"),
    "HKQuantityTypeIdentifierOxygenSaturation": (VitalType.SPO2, "%"),
    "HKQuantityTypeIdentifierBloodGlucose": (VitalType.BLOOD_GLUCOSE, "mg/dL"),
    "HKQuantityTypeIdentifierBodyMass": (VitalType.WEIGHT, "kg"),
    "HKQuantityTypeIdentifierBodyHeight": (VitalType.HEIGHT, "cm"),
    "HKQuantityTypeIdentifierBodyTemperature": (VitalType.TEMPERATURE, "°C"),
    "HKQuantityTypeIdentifierBloodPressureSystolic": (VitalType.BLOOD_PRESSURE, "mmHg"),
    "HKQuantityTypeIdentifierBloodPressureDiastolic": (VitalType.BLOOD_PRESSURE, "mmHg"),
}

# Apple fractional SpO2 (0.97) vs percent (97) — normalize to percent.
_FRACTIONAL_TYPES = {VitalType.SPO2}


def _parse_day(start: str) -> date | None:
    try:
        return datetime.fromisoformat(start.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _normalize(vtype: VitalType, value: float, unit: str) -> float | None:
    """Convert to our canonical unit; None when the value is not usable."""
    if vtype is VitalType.TEMPERATURE:
        u = (unit or "").lower()
        if u in ("degf", "°f", "f"):
            return round((value - 32) * 5 / 9, 1)
        if 45 < value <= 115:  # plausible °F band, unit omitted
            return round((value - 32) * 5 / 9, 1)
        if not (30 <= value <= 45):
            return None
        return round(value, 1)
    if vtype is VitalType.WEIGHT:
        u = (unit or "").lower()
        if u in ("lb", "lbs"):
            return round(value * 0.45359237, 1)
        if value <= 1:  # implausible kg body weight
            return None
        return round(value, 1)
    if vtype is VitalType.HEIGHT:
        u = (unit or "").lower()
        if u in ("in", "inch"):
            return round(value * 2.54, 1)
        if value <= 1:  # meters
            return round(value * 100, 1)
        return round(value, 1)
    if vtype is VitalType.SPO2 and value <= 1.0:
        return round(value * 100, 1)
    if value <= 0:
        return None
    return round(value, 1)


def aggregate_health_xml(data: bytes) -> dict:
    """Stream-parse Apple Health Export.xml → daily aggregates.

    Returns ``{read, vitals: [{vital_type, day, value, value_secondary,
    unit}], skipped_types: {identifier: count}}``. Pure — no DB.
    """
    # acc[(vital_type, day)] = {"values": [...], "diastolic": [...]}
    acc: dict[tuple[VitalType, date], dict] = defaultdict(lambda: {"values": [], "diastolic": []})
    skipped: dict[str, int] = defaultdict(int)
    read = 0

    parser = ET.iterparse(io.BytesIO(data), events=("end",))
    for _event, elem in parser:
        if not elem.tag.endswith("Record"):
            continue
        # Read everything BEFORE clear() — clear wipes attributes too. It
        # exists to bound memory (the root would otherwise hold every
        # parsed Record of a multi-hundred-MB export).
        rtype = elem.get("type") or ""
        mapping = _TYPE_MAP.get(rtype)
        if mapping is None:
            if rtype:
                skipped[rtype] += 1
            continue
        raw = elem.get("value")
        if raw is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            skipped[rtype] += 1
            continue
        day = _parse_day(elem.get("startDate") or "")
        if day is None:
            skipped[rtype] += 1
            continue
        vtype, unit = mapping
        normalized = _normalize(vtype, value, elem.get("unit") or "")
        if normalized is None:
            skipped[rtype] += 1
            continue
        read += 1
        bucket = acc[(vtype, day)]
        if vtype is VitalType.BLOOD_PRESSURE and rtype.endswith("Diastolic"):
            bucket["diastolic"].append(normalized)
        else:
            bucket["values"].append(normalized)
        elem.clear()  # free the element now that its attributes are consumed

    vitals: list[dict] = []
    for (vtype, day), bucket in acc.items():
        if bucket["values"]:
            value = round(mean(bucket["values"]), 1)
        else:
            continue  # a diastolic-only day carries nothing usable
        secondary = round(mean(bucket["diastolic"]), 1) if bucket["diastolic"] else None
        unit = next(u for t, u in _TYPE_MAP.values() if t is vtype)
        vitals.append(
            {
                "vital_type": vtype,
                "day": day,
                "value": value,
                "value_secondary": secondary,
                "unit": unit,
            }
        )
    return {"read": read, "vitals": vitals, "skipped_types": dict(skipped)}


def _day_as_datetime(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


async def apply_health_import(db: AsyncSession, member_id, aggregated: dict) -> dict:
    """Upsert daily rows idempotently: existing (member, type, day) updates.

    Matching happens in Python on the measured *date* — SQLite stores
    datetimes without tzinfo, so a SQL equality against a tz-aware value
    would silently miss rows.
    """
    existing_rows = list(
        await db.scalars(
            select(VitalMeasurement).where(
                VitalMeasurement.member_id == member_id,
                VitalMeasurement.source == "health_import",
            )
        )
    )
    by_key: dict[tuple[str, date], VitalMeasurement] = {}
    for row in existing_rows:
        by_key.setdefault((row.vital_type, row.measured_at.date()), row)

    created = 0
    updated = 0
    for v in aggregated["vitals"]:
        secondary = v["value_secondary"]
        key = (v["vital_type"].value, v["day"])
        existing = by_key.get(key)
        if existing is not None:
            existing.value_num = v["value"]
            existing.value_secondary = secondary
            existing.unit = v["unit"]
            updated += 1
            continue
        row = VitalMeasurement(
            member_id=member_id,
            vital_type=v["vital_type"].value,
            value_num=v["value"],
            value_secondary=secondary,
            unit=v["unit"],
            measured_at=_day_as_datetime(v["day"]),
            source="health_import",
        )
        db.add(row)
        by_key[key] = row
        created += 1
    return {"created": created, "updated": updated, "read": aggregated.get("read", 0)}
