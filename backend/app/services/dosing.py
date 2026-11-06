"""Dose scheduling: daily, PRN (as-needed), taper, and cycle regimens.

Pure functions — no DB access. `expand_day` answers "what doses are due on
this date?" and is the single source the pillbox and future sweeps use.

- daily: fixed slots, one dose each.
- prn: no scheduled doses (surface the med, never sweep it).
- taper: dose count steps down over time; annotation explains ("2 now —
  taper"); finished (0 doses) meds drop out of the schedule entirely.
- cycle: on/off blocks (e.g. 21 on / 7 off); off-day doses are skipped and
  must never be logged or swept as missed.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

# Six daily slots, defaults matching the printed schedule card. A medicine's
# own schedule_json.slot_times override these per slot.
SLOT_TIMES: dict[str, time] = {
    "morning": time(8, 30),
    "breakfast": time(9, 30),
    "noon": time(13, 0),
    "evening": time(18, 0),
    "dinner": time(21, 30),
    "bedtime": time(22, 30),
}

DEFAULT_SLOTS = ["morning", "evening"]


@dataclass(frozen=True)
class Dose:
    slot: str
    scheduled_time: datetime
    dose_count: int
    annotation: str | None


def parse_schedule(med) -> dict[str, Any]:  # noqa: ANN001 — ORM instance
    params = json.loads(med.schedule_json) if med.schedule_json else {}
    params.setdefault("slots", DEFAULT_SLOTS if med.schedule_type != "prn" else [])
    return params


def _day_doses(med, params: dict, day: date) -> int | None:  # noqa: ANN001
    """Effective dose count per slot for the day; None = off-day/cycle skip."""
    kind = med.schedule_type
    start = med.start_date or day
    if kind == "taper":
        step_days = max(int(params.get("step_every_days", 7)), 1)
        steps = max((day - start).days, 0) // step_days
        count = int(params.get("doses_start", 1)) + int(params.get("step", -1)) * steps
        return max(count, int(params.get("floor", 0)))
    if kind == "cycle":
        on = max(int(params.get("on_days", 21)), 1)
        off = max(int(params.get("off_days", 7)), 0)
        phase = max((day - start).days, 0) % (on + off)
        return 1 if phase < on else None
    return 1


def _slot_time(slot: str, params: dict) -> time | None:
    """Slot clock time: the medicine's own slot_times override wins over the
    household SLOT_TIMES default; unparseable overrides fall back."""
    override = (
        params.get("slot_times", {}).get(slot)
        if isinstance(params.get("slot_times"), dict)
        else None
    )
    if isinstance(override, str):
        try:
            hour, minute = override.strip().split(":")
            return time(int(hour), int(minute))
        except ValueError:
            pass
    return SLOT_TIMES.get(slot)


def expand_day(med, day: date) -> list[Dose]:  # noqa: ANN001
    """Doses due for one medication on one date. Finished taper → []."""
    if med.status != "active" or med.schedule_type == "prn":
        return []
    params = parse_schedule(med)
    count = _day_doses(med, params, day)
    if not count:  # 0 = taper finished; None = cycle off-day
        return []
    doses = []
    for slot in params["slots"]:
        slot_time = _slot_time(slot, params)
        if slot_time is None:
            continue
        annotation = f"{count} now — taper" if med.schedule_type == "taper" and count > 1 else None
        doses.append(
            Dose(
                slot=slot,
                scheduled_time=datetime.combine(day, slot_time),
                dose_count=count,
                annotation=annotation,
            )
        )
    return doses


def is_cycle_off_day(med, day: date) -> bool:  # noqa: ANN001
    if med.schedule_type != "cycle":
        return False
    return _day_doses(med, parse_schedule(med), day) is None
