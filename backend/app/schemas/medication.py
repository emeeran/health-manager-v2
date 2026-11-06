import json
import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.medication import MedicationStatus
from app.services.dosing import SLOT_TIMES
from app.schemas._datetime import UTCDateTime

VALID_SLOTS = set(SLOT_TIMES)


class TaperParams(BaseModel):
    doses_start: int = Field(ge=1, le=10)
    step: int = Field(default=-1, ge=-3, le=-1)
    step_every_days: int = Field(default=7, ge=1, le=365)
    floor: int = Field(default=0, ge=0, le=5)


class CycleParams(BaseModel):
    on_days: int = Field(ge=1, le=365)
    off_days: int = Field(default=7, ge=0, le=365)


class MedicationCreate(BaseModel):
    medicine: str = Field(min_length=1, max_length=200)
    # Source record (e.g. the prescription this came from) for traceability.
    record_id: uuid.UUID | None = None
    # Presentation form: Tab | Cap | Inj | Syp | Cream | Drops | Inhaler | Other.
    dose_form: str | None = Field(default=None, max_length=16)
    dosage: str | None = Field(default=None, max_length=120)
    timing: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    start_date: date | None = None
    schedule_type: str = Field(default="daily", pattern="^(daily|prn|taper|cycle)$")
    slots: list[str] | None = None
    # Per-slot clock overrides ("09:15") — a medicine's own times beat the
    # household SLOT_TIMES defaults in dosing.expand_day.
    slot_times: dict[str, str] | None = None
    provider_name: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    taper: TaperParams | None = None
    cycle: CycleParams | None = None

    def schedule_payload(self) -> str:
        params: dict = {}
        if self.slots:
            params["slots"] = clean_slots(self.slots)
        if self.slot_times:
            params["slot_times"] = clean_slot_times(self.slot_times)
        if self.schedule_type == "taper":
            if not self.taper:
                raise ValueError("taper params required for taper schedule")
            params |= self.taper.model_dump()
        if self.schedule_type == "cycle":
            if not self.cycle:
                raise ValueError("cycle params required for cycle schedule")
            params |= self.cycle.model_dump()
        return json.dumps(params)


class MedicationUpdate(BaseModel):
    # Widened for the schedule table's per-row Edit — every column the table
    # shows (medicine, form, dose, food/timing, duration, prescriber, times).
    medicine: str | None = Field(default=None, min_length=1, max_length=200)
    dose_form: str | None = Field(default=None, max_length=16)
    dosage: str | None = Field(default=None, max_length=120)
    timing: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    start_date: date | None = None
    end_date: date | None = None
    status: MedicationStatus | None = None
    provider_name: str | None = Field(default=None, max_length=200)
    # Schedule edits rebuild schedule_json on top of the stored params
    # (taper/cycle params are preserved).
    slots: list[str] | None = None
    slot_times: dict[str, str] | None = None


def clean_slots(slots: list[str]) -> list[str]:
    bad = set(slots) - VALID_SLOTS
    if bad:
        raise ValueError(f"unknown slots: {sorted(bad)}")
    return slots


def clean_slot_times(slot_times: dict[str, str]) -> dict[str, str]:
    bad_keys = set(slot_times) - VALID_SLOTS
    if bad_keys:
        raise ValueError(f"unknown slot_times keys: {sorted(bad_keys)}")
    cleaned: dict[str, str] = {}
    for key, value in slot_times.items():
        try:
            hh, mm = value.strip().split(":")
            hour, minute = int(hh), int(mm)
        except ValueError as exc:
            raise ValueError(f"invalid time for {key}: {value!r}") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"invalid time for {key}: {value!r}")
        cleaned[key] = f"{hour:02d}:{minute:02d}"
    return cleaned


def merge_schedule_update(
    existing_json: str | None,
    slots: list[str] | None,
    slot_times: dict[str, str] | None,
) -> str:
    """Rebuild schedule_json from the stored params plus edited slots/times."""
    params: dict = json.loads(existing_json) if existing_json else {}
    if slots is not None:
        if slots:
            params["slots"] = clean_slots(slots)
        else:
            params.pop("slots", None)
    if slot_times is not None:
        if slot_times:
            params["slot_times"] = clean_slot_times(slot_times)
        else:
            params.pop("slot_times", None)
    return json.dumps(params)


class MedicationResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    record_id: uuid.UUID | None
    medicine: str
    medicine_key: str
    dose_form: str | None
    dosage: str | None
    timing: str | None
    duration_days: int | None
    start_date: date | None
    end_date: date | None
    status: str
    schedule_type: str
    schedule_json: dict | None
    provider_name: str | None
    notes: str | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


def to_response(med) -> MedicationResponse:  # noqa: ANN001
    return MedicationResponse(
        id=med.id,
        member_id=med.member_id,
        record_id=med.record_id,
        medicine=med.medicine,
        medicine_key=med.medicine_key,
        dose_form=med.dose_form,
        dosage=med.dosage,
        timing=med.timing,
        duration_days=med.duration_days,
        start_date=med.start_date,
        end_date=med.end_date,
        status=med.status,
        schedule_type=med.schedule_type,
        schedule_json=(json.loads(med.schedule_json) if med.schedule_json else None),
        provider_name=med.provider_name,
        notes=med.notes,
        created_at=med.created_at,
    )
