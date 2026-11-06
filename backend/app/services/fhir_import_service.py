"""FHIR R4 bundle import (Phase 10, ported from v1's fhir_import_service).

Deliberately LENIENT parsing over raw dicts (real-world exports omit
"required" fields and mix R4/R4B element names) — every mapping failure
becomes a skip-with-reason instead of aborting the import. Structural
failures (not a Bundle, bad JSON) raise ``ValueError`` → 422 at the
router, never a partial write.

Mapping into v2's domain models:
  AllergyIntolerance              → Allergy
  Condition                       → ConditionEpisode
  Immunization                    → HealthRecord (record_type=vaccination)
  Observation                     → VitalMeasurement (BP pairs merged from
                                    sibling systolic/diastolic observations
                                    sharing an effective instant)
  MedicationRequest/Statement     → Medication rows
  DiagnosticReport                → LabResult
  Patient                         → skipped: import targets an existing member

IDEMPOTENCY: entities already present are skipped, matched on natural
keys per type (documented best-effort where no unique natural key exists):

  allergies     (member, lower(substance))
  conditions    (member, lower(name))
  vaccinations  (member, record content_hash of the synthetic record)
  vitals        (member, vital_type, measured day, value, value_secondary,
                 source="fhir_import")
  medications   (member, medicine_key, dosage, start_date)
  labs          (member, lower(test_name), record_date, result)
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    ConditionEpisode,
    HealthRecord,
    LabResult,
    Medication,
    RecordType,
    VitalMeasurement,
    VitalType,
    normalize_medicine_key,
)
from app.services.dedup_service import compute_content_hash

logger = logging.getLogger(__name__)

MAX_BUNDLE_BYTES = 20 * 1024 * 1024

_VITAL_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("systolic",), "systolic"),
    (("diastolic",), "diastolic"),
    (("blood pressure",), "blood_pressure"),
    (("heart rate", "pulse"), "heart_rate"),
    (("oxygen saturation", "spo2"), "spo2"),
    (("blood glucose", "glucose"), "blood_glucose"),
    (("temperature",), "temperature"),
    (("weight", "body mass"), "weight"),
    (("height",), "height"),
]

# FHIR vital keyword → v2 VitalType. Keywords missing from the table have
# no v2 enum member and are skipped with a reason (deviation from v1,
# which had respiratory_rate/waist).
_VITAL_TYPE_MAP: dict[str, VitalType] = {
    "blood_pressure": VitalType.BLOOD_PRESSURE,
    "heart_rate": VitalType.HEART_RATE,
    "spo2": VitalType.SPO2,
    "blood_glucose": VitalType.BLOOD_GLUCOSE,
    "temperature": VitalType.TEMPERATURE,
    "weight": VitalType.WEIGHT,
    "height": VitalType.HEIGHT,
}


def parse_bundle(data: bytes | str) -> dict:
    """Structural validation of untrusted input. ValueError on anything
    that isn't a collection/searchset/transaction bundle."""
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="strict")
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        raise ValueError("Not a FHIR Bundle (resourceType must be 'Bundle')")
    if (payload.get("type") or "").lower() not in (
        "collection",
        "searchset",
        "transaction",
    ):
        raise ValueError(f"Unsupported bundle type: {payload.get('type')}")
    if not isinstance(payload.get("entry"), list):
        raise ValueError("Bundle has no entries")
    return payload


def _concept_text(concept: Any) -> str:
    """CodeableConcept dict → best display text (text, then first coding)."""
    if not isinstance(concept, dict):
        return ""
    if concept.get("text"):
        return str(concept["text"])
    for coding in concept.get("coding") or []:
        if isinstance(coding, dict) and coding.get("display"):
            return str(coding["display"])
    return ""


def _as_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _as_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _vital_keyword(code_text: str) -> str | None:
    lowered = (code_text or "").lower()
    for keywords, key in _VITAL_KEYWORDS:
        if any(k in lowered for k in keywords):
            return key
    return None


def _severity_for_allergy(a: dict) -> str:
    for reaction in a.get("reaction") or []:
        if isinstance(reaction, dict) and reaction.get("severity"):
            return str(reaction["severity"]).lower()
    criticality = str(a.get("criticality") or "").lower()
    return {"low": "mild", "high": "severe"}.get(criticality, "moderate")


def _observation_values(obs: dict) -> list[tuple[str | None, float, str | None]]:
    """[(vital-key, value, unit)] from valueQuantity or coded BP components."""
    out: list[tuple[str | None, float, str | None]] = []
    code_text = _concept_text(obs.get("code"))
    q = obs.get("valueQuantity")
    if isinstance(q, dict) and isinstance(q.get("value"), int | float):
        key = _vital_keyword(code_text)
        out.append((key, float(q["value"]), str(q.get("unit") or "") or None))
    for comp in obs.get("component") or []:
        if not isinstance(comp, dict):
            continue
        cq = comp.get("valueQuantity")
        if not isinstance(cq, dict) or not isinstance(cq.get("value"), int | float):
            continue
        key = _vital_keyword(_concept_text(comp.get("code")))
        if key in ("systolic", "diastolic", "blood_pressure"):
            out.append((key, float(cq["value"]), str(cq.get("unit") or "mmHg")))
    return out


def stage_bundle(bundle: dict) -> dict:
    """Map supported resources to proposed rows. Pure — no DB, no writes."""
    staged: dict[str, Any] = {
        "allergies": [],
        "conditions": [],
        "vaccinations": [],
        "vitals": [],
        "medications": [],
        "labs": [],
        "skipped": [],
    }
    systolic_by_instant: dict[str, dict] = {}
    diastolic_by_instant: dict[str, dict] = {}

    def _skip(rtype: str, reason: str, summary: str = "") -> None:
        staged["skipped"].append({"type": rtype, "reason": reason, "summary": summary[:80]})

    for entry in bundle.get("entry") or []:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        rtype = str(resource.get("resourceType") or "")

        if rtype == "Patient":
            _skip("Patient", "import targets the selected member")
        elif rtype == "AllergyIntolerance":
            substance = _concept_text(resource.get("code"))
            if not substance:
                _skip(rtype, "no substance code")
                continue
            reaction = ""
            for r in resource.get("reaction") or []:
                for m in (r.get("manifestation") or []) if isinstance(r, dict) else []:
                    text = _concept_text(m) if isinstance(m, dict) else str(m)
                    if text:
                        reaction = text if not reaction else f"{reaction}, {text}"
                if reaction:
                    break
            staged["allergies"].append(
                {
                    "substance": substance,
                    "severity": _severity_for_allergy(resource),
                    "reaction": reaction or None,
                }
            )
        elif rtype == "Condition":
            name = _concept_text(resource.get("code"))
            if not name:
                _skip(rtype, "no code")
                continue
            status_code = "active"
            clinical = resource.get("clinicalStatus") or {}
            for coding in clinical.get("coding") or []:
                if isinstance(coding, dict) and coding.get("code"):
                    status_code = str(coding["code"]).lower()
                    break
            staged["conditions"].append(
                {
                    "name": name,
                    "status": status_code,
                    "onset_date": _as_date(resource.get("onsetDateTime")),
                    "resolution_date": _as_date(resource.get("abatementDateTime")),
                }
            )
        elif rtype == "Immunization":
            name = _concept_text(resource.get("vaccineCode")) or str(
                resource.get("occurrenceString") or ""
            )
            if not name:
                _skip(rtype, "no vaccine code or occurrence")
                continue
            staged["vaccinations"].append(
                {
                    "name": name,
                    "date_administered": _as_date(resource.get("occurrenceDateTime")),
                }
            )
        elif rtype == "Observation":
            values = _observation_values(resource)
            effective = resource.get("effectiveDateTime")
            measured_dt = _as_datetime(effective)
            measured = _as_date(effective) or _as_date(
                (resource.get("effectivePeriod") or {}).get("start")
            )
            if not values:
                _skip(
                    rtype,
                    "no recognizable vital or numeric value",
                    _concept_text(resource.get("code")),
                )
                continue
            for key, value, unit in values:
                entry_data = {
                    "kind": key or "blood_pressure",
                    "value": value,
                    "value_secondary": None,
                    "unit": unit,
                    "measured_at": measured,
                    "measured_dt": measured_dt,
                    "text": _concept_text(resource.get("code")),
                }
                if key == "systolic":
                    systolic_by_instant.setdefault(str(effective or ""), entry_data)
                elif key == "diastolic":
                    diastolic_by_instant.setdefault(str(effective or ""), entry_data)
                else:
                    staged["vitals"].append(entry_data)
        elif rtype in ("MedicationRequest", "MedicationStatement"):
            med = resource.get("medicationCodeableConcept")
            med_text = _concept_text(med) if isinstance(med, dict) else ""
            if not med_text:
                med = resource.get("medication")  # R4B choice element
                med_text = _concept_text(med) if isinstance(med, dict) else ""
            if not med_text:
                _skip(rtype, "no medication code")
                continue
            dosage = ""
            timing = ""
            for instruction in resource.get("dosageInstruction") or []:
                if not isinstance(instruction, dict):
                    continue
                dosage = str(instruction.get("text") or dosage)
                timing_code = (instruction.get("timing") or {}).get("code") or {}
                timing = str(_concept_text(timing_code) or timing)
                if instruction.get("asNeededBoolean") or instruction.get("asNeededCodeableConcept"):
                    timing = timing or "sos"
                if dosage:
                    break
            staged["medications"].append(
                {
                    "medicine": med_text,
                    "dosage": dosage,
                    "timing": timing,
                    "start_date": _as_date(resource.get("authoredOn")),
                }
            )
        elif rtype == "DiagnosticReport":
            test_name = _concept_text(resource.get("code"))
            if not test_name:
                _skip(rtype, "no code")
                continue
            staged["labs"].append(
                {
                    "test_name": test_name,
                    "result": str(resource.get("conclusion") or "")[:500],
                    "record_date": _as_date(resource.get("effectiveDateTime")),
                }
            )
        # Anything else (Encounter, Organization, …) is silently ignored.

    # Merge sibling systolic/diastolic observations sharing an instant → BP.
    for instant, sys_data in systolic_by_instant.items():
        dia = diastolic_by_instant.pop(instant, None)
        staged["vitals"].append(
            {
                "kind": "blood_pressure",
                "value": sys_data["value"],
                "value_secondary": dia["value"] if dia else None,
                "unit": "mmHg",
                "measured_at": sys_data["measured_at"],
                "measured_dt": sys_data["measured_dt"],
                "text": sys_data.get("text", "blood pressure"),
            }
        )
    for instant, _dia in diastolic_by_instant.items():
        _skip("Observation", "diastolic without a matching systolic", instant)

    staged["counts"] = {
        key: len(staged[key])
        for key in ("allergies", "conditions", "vaccinations", "vitals", "medications", "labs")
    }
    return staged


def _condition_status(fhir_status: str) -> str:
    """FHIR clinicalStatus code → v2 ConditionStatus value."""
    mapping = {
        "active": "active",
        "recurrence": "active",
        "relapse": "active",
        "remission": "resolved",
        "resolved": "resolved",
        "inactive": "resolved",
    }
    return mapping.get(fhir_status, "active")


async def apply_staged(db: AsyncSession, member_id, staged: dict) -> dict:
    """Write every staged section, skipping entities already present.

    Returns ``{"created": {section: n}, "skipped_existing": {section: n},
    "skipped": [{type, reason, summary}]}``.
    """
    created: dict[str, int] = defaultdict(int)
    skipped_existing: dict[str, int] = defaultdict(int)

    async def _exists(model, *conditions) -> bool:
        row = await db.scalar(select(model.id).where(*conditions).limit(1))
        return row is not None

    # Allergies — natural key (member, lower(substance)). substance is
    # encrypted at rest, so the key comparison happens in Python.
    existing_substances = {
        (a.substance or "").strip().lower()
        for a in (await db.scalars(select(Allergy).where(Allergy.member_id == member_id)))
    }
    for a in staged["allergies"]:
        if a["substance"].strip().lower() in existing_substances:
            skipped_existing["allergies"] += 1
            continue
        db.add(
            Allergy(
                member_id=member_id,
                substance=a["substance"][:200],
                severity=a["severity"],
                reaction=a["reaction"],
            )
        )
        created["allergies"] += 1
        existing_substances.add(a["substance"].strip().lower())

    # Conditions — natural key (member, lower(name)).
    existing_names = {
        (c.name or "").strip().lower()
        for c in (
            await db.scalars(
                select(ConditionEpisode).where(ConditionEpisode.member_id == member_id)
            )
        )
    }
    for c in staged["conditions"]:
        key = c["name"].strip().lower()
        if key in existing_names:
            skipped_existing["conditions"] += 1
            continue
        db.add(
            ConditionEpisode(
                member_id=member_id,
                name=c["name"][:200],
                status=_condition_status(c["status"]),
                onset_date=c["onset_date"],
                resolution_date=c["resolution_date"],
            )
        )
        created["conditions"] += 1
        existing_names.add(key)

    # Vaccinations — synthetic vaccination records dedupe on content hash.
    existing_hashes = set(
        await db.scalars(
            select(HealthRecord.content_hash).where(
                HealthRecord.member_id == member_id,
                HealthRecord.record_type == RecordType.VACCINATION.value,
            )
        )
    )
    for v in staged["vaccinations"]:
        day = v["date_administered"] or date.today()
        payload = {"vaccine": v["name"]}
        content_hash = compute_content_hash(RecordType.VACCINATION.value, day, payload)
        if content_hash in existing_hashes:
            skipped_existing["vaccinations"] += 1
            continue
        db.add(
            HealthRecord(
                member_id=member_id,
                record_type=RecordType.VACCINATION.value,
                record_date=day,
                summary=v["name"][:200],
                content_hash=content_hash,
            )
        )
        created["vaccinations"] += 1
        existing_hashes.add(content_hash)

    # Vitals — natural key (member, type, measured day, value, secondary)
    # within the fhir_import source. Compared in Python so timezone-naive
    # SQLite storage can't break the match.
    existing_vitals = list(
        await db.scalars(
            select(VitalMeasurement).where(
                VitalMeasurement.member_id == member_id,
                VitalMeasurement.source == "fhir_import",
            )
        )
    )
    seen_vital_keys = {
        (
            v.vital_type,
            v.measured_at.date(),
            round(v.value_num, 1),
            round(v.value_secondary, 1) if v.value_secondary is not None else None,
        )
        for v in existing_vitals
    }
    for v in staged["vitals"]:
        vtype = _VITAL_TYPE_MAP.get(v["kind"])
        if vtype is None:
            staged["skipped"].append(
                {
                    "type": "Observation",
                    "reason": f"no v2 vital type for '{v['kind']}'",
                    "summary": v.get("text", ""),
                }
            )
            continue
        measured = v.get("measured_dt") or v.get("measured_at")
        if measured is None:
            staged["skipped"].append(
                {"type": "Observation", "reason": "no effective date", "summary": ""}
            )
            continue
        secondary = v.get("value_secondary")
        key = (
            vtype.value,
            measured.date(),
            round(v["value"], 1),
            round(secondary, 1) if secondary is not None else None,
        )
        if key in seen_vital_keys:
            skipped_existing["vitals"] += 1
            continue
        db.add(
            VitalMeasurement(
                member_id=member_id,
                vital_type=vtype.value,
                value_num=v["value"],
                value_secondary=secondary,
                unit=v.get("unit") or "mmHg",
                measured_at=measured,
                source="fhir_import",
            )
        )
        created["vitals"] += 1
        seen_vital_keys.add(key)

    # Medications — natural key (member, medicine_key, dosage, start_date).
    existing_meds = list(
        await db.scalars(select(Medication).where(Medication.member_id == member_id))
    )
    seen_med_keys = {
        (m.medicine_key, (m.dosage or "").lower(), m.start_date) for m in existing_meds
    }
    for m in staged["medications"]:
        if not isinstance(m, dict):
            continue
        key = (
            normalize_medicine_key(m["medicine"]),
            (m["dosage"] or "").lower(),
            m["start_date"],
        )
        if key in seen_med_keys:
            skipped_existing["medications"] += 1
            continue
        db.add(
            Medication(
                member_id=member_id,
                medicine=m["medicine"][:200],
                medicine_key=normalize_medicine_key(m["medicine"]),
                dosage=m["dosage"][:120] if m["dosage"] else None,
                timing=m["timing"] or None,
                start_date=m["start_date"],
            )
        )
        created["medications"] += 1
        seen_med_keys.add(key)

    # Labs — natural key (member, lower(test_name), record_date, result).
    existing_labs = list(
        await db.scalars(select(LabResult).where(LabResult.member_id == member_id))
    )
    seen_lab_keys = {
        (
            (row.test_name or "").strip().lower(),
            row.record_date,
            (row.result or "").strip().lower(),
        )
        for row in existing_labs
    }
    for lab in staged["labs"]:
        if lab["record_date"] is None:
            staged["skipped"].append(
                {
                    "type": "DiagnosticReport",
                    "reason": "no effective date",
                    "summary": lab["test_name"],
                }
            )
            continue
        key = (
            lab["test_name"].strip().lower(),
            lab["record_date"],
            (lab["result"] or "").strip().lower(),
        )
        if key in seen_lab_keys:
            skipped_existing["labs"] += 1
            continue
        db.add(
            LabResult(
                member_id=member_id,
                test_name=lab["test_name"][:200],
                result=lab["result"] or None,
                record_date=lab["record_date"],
            )
        )
        created["labs"] += 1
        seen_lab_keys.add(key)

    return {
        "created": dict(created),
        "skipped_existing": dict(skipped_existing),
        "skipped": staged["skipped"],
    }
