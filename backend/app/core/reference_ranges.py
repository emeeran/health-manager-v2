"""Reference ranges for vitals + common labs (guideline bands, read-only).

Every band carries a full guideline citation (source org / document /
year / URL) alongside the short ``citation`` label, so any number the UI
or the anomaly logic reasons from can be traced to its guideline. Ranges
are ADULT values.
"""

# Guideline citations (shared dicts — one source per guideline).
_ACC_AHA = {
    "org": "American College of Cardiology / American Heart Association",
    "document": "2017 ACC/AHA Hypertension Clinical Practice Guideline",
    "year": 2017,
    "url": "https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065",
}
_ADA = {
    "org": "American Diabetes Association",
    "document": "Standards of Care in Diabetes — Diagnosis",
    "year": 2026,
    "url": "https://diabetes.org/about-diabetes/diagnosis",
}
_ADA_LIPIDS = {
    "org": "American Diabetes Association",
    "document": "Standards of Care in Diabetes — Lipid management",
    "year": 2026,
    "url": "https://diabetes.org/about-diabetes",
}
_WHO_HBA1C = {
    "org": "American Diabetes Association",
    "document": "Standards of Care in Diabetes — Classification and Diagnosis",
    "year": 2026,
    "url": "https://diabetes.org/about-diabetes/diagnosis",
}


def _bp_band(
    label: str, max_systolic: int | None, max_diastolic: int | None, color_key: str
) -> dict:
    return {
        "label": label,
        "max_systolic": max_systolic,
        "max_diastolic": max_diastolic,
        "color_key": color_key,
        "citation": "AHA 2017",
        "source": dict(_ACC_AHA),
    }


BP_BANDS: list[dict] = [
    _bp_band("Normal", 120, 80, "ok"),
    _bp_band("Elevated", 129, 80, "warning"),
    _bp_band("High BP (Stage 1)", 139, 89, "warning"),
    _bp_band("High BP (Stage 2)", 180, 120, "danger"),
    _bp_band("Hypertensive crisis", None, None, "danger"),
]

GLUCOSE_RANGES = {
    "fasting": {
        "normal_low": 70,
        "normal_high": 99,
        "unit": "mg/dL",
        "citation": "ADA Standards of Care",
        "source": dict(_ADA),
    },
    "post_prandial": {
        "normal_low": 70,
        "normal_high": 140,
        "unit": "mg/dL",
        "citation": "ADA Standards of Care",
        "source": dict(_ADA),
    },
}

# Common lab bands (adult); the lab anomaly notes cite these.
LAB_RANGES: dict[str, dict] = {
    "hba1c": {
        "test_name": "HbA1c",
        "normal_low": 4.0,
        "normal_high": 5.6,
        "unit": "%",
        "citation": "ADA Standards of Care",
        "source": dict(_WHO_HBA1C),
    },
    "ldl_cholesterol": {
        "test_name": "LDL cholesterol",
        "normal_low": 0,
        "normal_high": 100,
        "unit": "mg/dL",
        "citation": "ADA Standards of Care (lipid management)",
        "source": dict(_ADA_LIPIDS),
    },
}


def bp_stage(systolic: float, diastolic: float) -> dict:
    for band in BP_BANDS:
        s_max = band["max_systolic"]
        d_max = band["max_diastolic"]
        if (
            (s_max is None or systolic <= s_max)
            and (d_max is None or diastolic <= d_max)
            and band["label"] != "Hypertensive crisis"
        ):
            return band
    return BP_BANDS[-1]


def all_ranges() -> dict:
    return {
        "blood_pressure": {"bands": BP_BANDS},
        "blood_glucose": GLUCOSE_RANGES,
        "labs": LAB_RANGES,
    }
