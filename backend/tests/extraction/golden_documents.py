"""Golden documents for extraction evaluation.

Each golden doc: source text, the LLM-fake's canned reply (deterministic,
deliberately imperfect), and the expected structured extraction. The fake
reply is what CI scores; --real-ai swaps in a live provider.
"""

from datetime import date

GOLDEN_LAB_REPORT = {
    "name": "cbc_metabolic_panel",
    "mime": "application/pdf",
    "text": (
        "GREENVALLEY DIAGNOSTIC LABORATORY\n"
        "Patient: Asha Kumar        Report Date: 2026-03-14\n"
        "Referring Doctor: Dr. Meera Iyer\n\n"
        "COMPLETE BLOOD COUNT / METABOLIC PANEL\n"
        "Hemoglobin: 9.8 g/dL (Reference: 12.0-15.5) — LOW\n"
        "WBC: 11.2 x10^3/uL (Reference: 4.0-11.0) — HIGH\n"
        "Platelets: 250 x10^3/uL (Reference: 150-400) — NORMAL\n"
        "HbA1c: 8.1 % (Reference: 4.0-5.6) — HIGH\n"
    ),
    # Canned LLM reply — misses platelets (tests recall penalty).
    "fake_reply": (
        '{"record_date": "2026-03-14", "doctor_name": "Dr. Meera Iyer", '
        '"facility": "Greenvalley Diagnostic Laboratory", "diagnosis": null, '
        '"summary": "CBC showing anemia and leukocytosis; HbA1c elevated.", '
        '"medications": [], '
        '"labs": ['
        '{"name": "Hemoglobin", "result": "9.8", "units": "g/dL", '
        '"reference": "12.0-15.5", "flag": "low"},'
        '{"name": "WBC", "result": "11.2", "units": "x10^3/uL", '
        '"reference": "4.0-11.0", "flag": "high"},'
        '{"name": "HbA1c", "result": "8.1", "units": "%", '
        '"reference": "4.0-5.6", "flag": "high"}], "vitals": []}'
    ),
    "expected": {
        "record_date": date(2026, 3, 14).isoformat(),
        "doctor_name": "Dr. Meera Iyer",
        "labs": [
            {"name": "hemoglobin", "result": "9.8", "units": "g/dL", "flag": "low"},
            {"name": "wbc", "result": "11.2", "units": "x10^3/uL", "flag": "high"},
            {"name": "platelets", "result": "250", "units": "x10^3/uL", "flag": "normal"},
            {"name": "hba1c", "result": "8.1", "units": "%", "flag": "high"},
        ],
    },
}

GOLDEN_PRESCRIPTION = {
    "name": "diabetes_prescription",
    "mime": "application/pdf",
    "text": (
        "CITY CARE CLINIC — OUTPATIENT PRESCRIPTION\n"
        "Date: 2026-04-02\n"
        "Patient: Asha Kumar\n"
        "Doctor: Dr. Rahul Verma, MD (Endocrinology)\n\n"
        "Diagnosis: Type 2 Diabetes Mellitus\n\n"
        "Rx:\n"
        "1. Tab. Metformin 500 mg — twice daily after food × 30 days\n"
        "2. Tab. Glimepiride 1 mg — once daily before breakfast × 30 days\n\n"
        "Advice: daily fasting glucose log; review after 1 month.\n"
    ),
    # Canned reply — wrong duration on metformin (tests field accuracy).
    "fake_reply": (
        '{"record_date": "2026-04-02", "doctor_name": "Dr. Rahul Verma", '
        '"facility": "City Care Clinic", '
        '"diagnosis": "Type 2 Diabetes Mellitus", '
        '"summary": "New-onset T2DM started on oral hypoglycemics.", '
        '"medications": ['
        '{"name": "Metformin", "dosage": "500 mg", '
        '"timing": "twice daily after food", "duration_days": 14},'
        '{"name": "Glimepiride", "dosage": "1 mg", '
        '"timing": "once daily before breakfast", "duration_days": 30}], '
        '"labs": [], "vitals": []}'
    ),
    "expected": {
        "record_date": date(2026, 4, 2).isoformat(),
        "doctor_name": "Dr. Rahul Verma",
        "diagnosis": "Type 2 Diabetes Mellitus",
        "medications": [
            {"name": "metformin", "dosage": "500 mg", "duration_days": 30},
            {"name": "glimepiride", "dosage": "1 mg", "duration_days": 30},
        ],
    },
}

GOLDEN_DOCUMENTS = [GOLDEN_LAB_REPORT, GOLDEN_PRESCRIPTION]
