"""Pediatric growth engine (Wave 6.1) — CDC 2000 LMS percentiles.

LMS tables load once from ``app/data/growth/*.csv`` (provenance in the
README next to them) into indicator-keyed rows; lookups linearly
interpolate L/M/S across age, then

    z = ((value / M)^L − 1) / (L · S)      (z = ln(v/M)/S when L ≈ 0)
    percentile = 100 · Φ(z)                (erf, no scipy dependency)

|z| > 5 is flagged implausible and clamped for display — recording
errors (a 40 kg toddler) shouldn't render as −99th percentile.

Age basis: months = days since birth / 30.4375 (the CDC tables' Agemos
convention). Length vs stature follows the measurement: recumbent
length < 24 months, standing stature ≥ 24 — the caller (or member meta)
says which was measured; the default follows the age rule.
"""

import csv
import logging
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "growth"


@dataclass(frozen=True)
class LmsPoint:
    """One row of the CDC table. Field names follow the LMS convention
    (L = Box-Cox power, M = median, S = coefficient of variation)."""

    age_months: float
    l: float  # noqa: E741 — the L in LMS
    m: float
    s: float


class Indicator:
    WEIGHT = "weight"
    LENGTH = "length"
    STATURE = "stature"
    HEAD_CIRCUMFERENCE = "head_circumference"
    BMI = "bmi"


_FILES = {
    Indicator.WEIGHT: "wtageinf.csv",
    Indicator.LENGTH: "lenageinf.csv",
    Indicator.HEAD_CIRCUMFERENCE: "hcageinf.csv",
    Indicator.STATURE: "statage.csv",
    Indicator.BMI: "bmiagerev.csv",
}


def _load() -> dict[str, dict[int, list[LmsPoint]]]:
    tables: dict[str, dict[int, list[LmsPoint]]] = {}
    for indicator, filename in _FILES.items():
        path = _DATA_DIR / filename
        by_sex: dict[int, list[LmsPoint]] = {1: [], 2: []}
        # CDC files ship CRLF; normalize so DictReader keys are clean.
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        for row in csv.DictReader(text.splitlines()):
            # Some files repeat the header row between the boys/girls
            # sections — skip anything that isn't a data row.
            if not (row.get("Sex") or "").strip().isdigit():
                continue
            sex = int(row["Sex"])
            by_sex[sex].append(
                LmsPoint(
                    age_months=float(row["Agemos"]),
                    l=float(row["L"]),
                    m=float(row["M"]),
                    s=float(row["S"]),
                )
            )
        for points in by_sex.values():
            points.sort(key=lambda p: p.age_months)
        tables[indicator] = by_sex
    return tables


_TABLES = _load()


def lms_for(indicator: str, sex: int, age_months: float) -> LmsPoint:
    """L/M/S at ``age_months``, linearly interpolated between table rows.

    Sex: 1 = boy, 2 = girl (CDC convention). Age outside the table's span
    (e.g. weight-for-age past 36 months) raises ValueError — the caller
    decides to skip or switch indicators.
    """
    points = _TABLES[indicator][sex]
    if not points:
        raise ValueError(f"no LMS table for {indicator}")
    if age_months < points[0].age_months or age_months > points[-1].age_months:
        raise ValueError(
            f"{indicator} applies to {points[0].age_months}–{points[-1].age_months} months"
        )
    for point in points:
        if point.age_months == age_months:
            return point
    for i in range(len(points) - 1):
        lo, hi = points[i], points[i + 1]
        if lo.age_months < age_months < hi.age_months:
            t = (age_months - lo.age_months) / (hi.age_months - lo.age_months)
            return LmsPoint(
                age_months=age_months,
                l=lo.l + t * (hi.l - lo.l),
                m=lo.m + t * (hi.m - lo.m),
                s=lo.s + t * (hi.s - lo.s),
            )
    return points[-1]


def z_score(value: float, point: LmsPoint) -> float:
    if value <= 0:
        # Non-positive measurements would make the Box-Cox power return a
        # complex number (negative base, fractional L) — the caller skips
        # them as implausible rather than 500ing the report.
        raise ValueError(f"non-positive measurement: {value}")
    if abs(point.l) < 1e-8:  # L≈0 (normal-distribution case, e.g. BMI tables)
        return math.log(value / point.m) / point.s
    return float(((value / point.m) ** point.l - 1.0) / (point.l * point.s))


def percentile_for(z: float) -> float:
    return float(100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))


def assess(indicator: str, sex: int, age_months: float, value: float) -> dict:
    """z-score + percentile for one measurement, with plausibility flag."""
    point = lms_for(indicator, sex, age_months)
    z = z_score(value, point)
    implausible = abs(z) > 5
    return {
        "indicator": indicator,
        "age_months": round(age_months, 2),
        "value": value,
        "lms": {"l": round(point.l, 5), "m": round(point.m, 4), "s": round(point.s, 5)},
        "z": round(min(max(z, -5.0), 5.0), 2),
        "percentile": round(min(max(percentile_for(z), 0.1), 99.9), 1),
        "implausible": implausible,
    }


def age_months_on(dob: date, on: date) -> float:
    """Age in CDC-convention months between two dates."""
    return (on - dob).days / 30.4375
