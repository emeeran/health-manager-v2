"""Growth router — pediatric percentiles per member.

GET /members/{id}/growth/report
    The member's weight / length-stature / head-circumference readings
    from the vitals series, each assessed against the CDC LMS reference
    at the reading's age. BMI is computed from paired weight+height when
    no explicit BMI exists. Members past 20y get an empty report — the
    reference tables end at 240 months.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Literal

from app.core.database import get_db
from app.core.deps import get_current_user, get_scoped_member
from app.models import User
from app.models.member import FamilyMember
from app.models.vital import VitalMeasurement, VitalType
from app.services.growth_service import Indicator, age_months_on, assess

router = APIRouter(prefix="/members/{member_id}/growth", tags=["growth"])

# CDC tables end at 240 months (20y).
MAX_AGE_MONTHS = 240.0

# vital type → indicator; length vs stature is resolved per reading age.
_VITAL_INDICATORS = {
    VitalType.WEIGHT.value: Indicator.WEIGHT,
    VitalType.HEIGHT.value: None,  # resolved per age: length < 24mo, stature ≥
    VitalType.HEAD_CIRCUMFERENCE.value: Indicator.HEAD_CIRCUMFERENCE,
}


def _indicator_for_height(age_months: float) -> str:
    return Indicator.LENGTH if age_months < 24 else Indicator.STATURE


def _sex_code(member: FamilyMember, override: str | None) -> int:
    """Member sex → CDC sex code (1 boy, 2 girl); the request may override."""
    sex = (override or member.sex or "").lower()
    if sex == "female":
        return 2
    return 1  # male / other / unknown — the UI can override per child


@router.get("/report")
async def growth_report(
    member_id: uuid.UUID,
    sex: Literal["male", "female"] | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Percentile assessment of the member's growth measurements."""
    member: FamilyMember = await get_scoped_member(member_id, user, db)
    if member.birth_date is None:
        return {"age_months": None, "rows": [], "note": "date of birth unknown"}
    sex_code = _sex_code(member, sex)
    as_of = date.today()
    age_months = age_months_on(member.birth_date, as_of)
    if age_months > MAX_AGE_MONTHS:
        return {
            "age_months": round(age_months, 1),
            "rows": [],
            "note": "reference tables end at 240 months (20 years)",
        }

    readings = list(
        await db.scalars(
            select(VitalMeasurement)
            .where(VitalMeasurement.member_id == member_id)
            .where(
                VitalMeasurement.vital_type.in_(
                    [
                        VitalType.WEIGHT.value,
                        VitalType.HEIGHT.value,
                        VitalType.HEAD_CIRCUMFERENCE.value,
                    ]
                )
            )
            .order_by(VitalMeasurement.measured_at)
        )
    )

    # BMI from the latest weight + height pair (within 30 days of each other).
    weights = [r for r in readings if r.vital_type == VitalType.WEIGHT.value]
    heights = [r for r in readings if r.vital_type == VitalType.HEIGHT.value]
    bmi_row: dict[str, Any] | None = None
    if weights and heights:
        latest_w = weights[-1]
        nearest_h = min(heights, key=lambda h: abs((h.measured_at - latest_w.measured_at).days))
        if (
            latest_w.value_num > 0
            and nearest_h.value_num > 0
            and abs((nearest_h.measured_at - latest_w.measured_at).days) <= 30
        ):
            height_m = nearest_h.value_num / 100.0
            bmi_row = {
                "measured_on": latest_w.measured_at.date(),
                "bmi": round(latest_w.value_num / (height_m * height_m), 1),
            }

    rows: list[dict] = []
    for reading in readings:
        try:
            reading_age = age_months_on(member.birth_date, reading.measured_at.date())
            if reading_age > MAX_AGE_MONTHS:
                continue
            indicator = (
                _indicator_for_height(reading_age)
                if reading.vital_type == VitalType.HEIGHT.value
                else _VITAL_INDICATORS[reading.vital_type]
            )
            assert indicator is not None  # HEIGHT maps to None only in the dict
            assessment = assess(indicator, sex_code, reading_age, reading.value_num)
            rows.append(
                {
                    "measure": indicator,
                    "measured_at": reading.measured_at.isoformat(),
                    "value": reading.value_num,
                    **assessment,
                }
            )
        except ValueError:
            # Reading older/younger than that indicator's table — skip quietly.
            continue

    if bmi_row is not None and age_months >= 24:
        try:
            bmi_age = age_months_on(member.birth_date, bmi_row["measured_on"])
            assessment = assess(Indicator.BMI, sex_code, bmi_age, bmi_row["bmi"])
            rows.append(
                {
                    "measure": Indicator.BMI,
                    "measured_at": bmi_row["measured_on"].isoformat(),
                    "value": bmi_row["bmi"],
                    **assessment,
                }
            )
        except ValueError:
            pass

    return {"age_months": round(age_months, 2), "as_of": as_of.isoformat(), "rows": rows}
