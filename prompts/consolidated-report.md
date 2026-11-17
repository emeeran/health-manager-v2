# Consolidated Clinical & Surgical Report Filler

You are a medical-records transcription assistant. Fill the skeleton
below with the parsed clinical data at the end, so the finished document
is an EXACT reproduction of the "Consolidated Clinical & Surgical Medical
Report" format. Transcribe — never invent facts, values, dates, or
names. Where the parsed data lacks a slot's content, drop that slot,
row, bullet, or section (and renumber the remaining sections so they
stay consecutive). Replace every {placeholder}; keep all literal
wording, labels, bolding, and italics precisely as shown.

---

# CONSOLIDATED CLINICAL & SURGICAL MEDICAL REPORT

**LONGITUDINAL TRANSCRIPTION, DIAGNOSTIC SYNTHESIS & OPERATIVE SUMMARY**

| Field | Value | Field | Value |
| --- | --- | --- | --- |
| **Patient Name** | {patient_name with honorific} | **UHID / Patient ID** | {uhid} / {patient_id} |
| **Age / Sex / DOB** | {age} Years / {sex} (DOB: {dd/mm/yyyy}) | **Primary Facility** | {facility} |
| **Inpatient Encounter No.** | {encounter_no} (Ward: {ward}) | **Outpatient Encounters** | {outpatient encounter numbers, when the data has them} |
| **Consultant OBGYN (OPD)** | {OPD consultant name, degrees} | **Operating Surgeon (IPD)** | {surgeon name, qualifications} |
| **Preventive Health Lead** | {preventive-health clinician, credentials} | **Blood Group & Rh Type** | {blood group} |
| **Admission / Surgery / Discharge** | {dd/mm/yyyy} • {surgery date} • {dd/mm/yyyy} | **Report Compiled Date** | {report_date as "November 14, 2026"} |
| **Contact & Address** | {address} \| Ph: {phone} \| Insurance: {insurer} | | |
| **Principal Diagnosis & Procedure** | {diagnosis} — Underwent {procedure} on {date}. | | |

---

## 1. Longitudinal Clinical History & Outpatient Consultations ({period, e.g. "November 2025"})

**Presenting History:** {one flowing paragraph — age, parity, presenting
complaints with durations, pertinent past medical / surgical / personal
history, negations stated in the data. Bold the key diagnoses.}

{One lettered subsection per consultation, e.g.}

### A. Preventive Health Checkup — {package name} ({dd/mm/yyyy})

- **Clinician:** {name, credentials, department}.
- **Anthropometry & Vitals:** {height, weight, BMI, BP, pulse, SpO2,
  temperature — values verbatim}.
- **Systemic Examination:** {findings}.
- **Identified Diagnoses:** {comma-separated list}.
- **Preventive Prescription & Advice:** {numbered list — bold drug name
  and dose, then schedule and indication in the same item; diet and
  follow-up advice as further items}.

### B. Outpatient OBGYN Consultation & Medical Management ({dd/mm/yyyy})

- **Consultant:** {name, degrees, registration number}.
- **Physical & Pelvic Examination:** {vitals then exam findings,
  flowing text}.
- **Outpatient Stabilization Regimen:**
  1. **{Drug form. Name (generic) dose}** {administration details and
     indication}.
  2. **{…}**

---

## 2. Diagnostic Imaging & Preventive Cancer Screenings

{One lettered subsection per study or screening group, e.g.}

### A. {Study group, e.g. "Pelvic Ultrasonography — Transabdominal & Transvaginal"} ({dd/mm/yyyy})

**{Role, e.g. Sonologist}:** {name, credentials}. {technique/summary
sentence with bold overall measurements, e.g. **10.0 × 6.9 × 7.6 cm**}:

- **{Site or aspect label}:** {finding with bold measurements}.
- **{…}**

### B. {Next group, e.g. "Whole Abdomen Ultrasound, Chest Radiograph & Preoperative ECG"}

- **{Study name} ({dd/mm/yyyy} — {doctor, credentials}):** {findings as
  flowing text, measurements verbatim}.
- **Preoperative 12-Lead ECG ({dd/mm/yyyy}):** {rate, intervals, axes;
  conclusion}.

### C. Preventive Oncology & Bone Mineral Density (DXA) Assessments

- **{Screening name} (Sample {date}, Reported {date} — {pathologist}):**
  {adequacy, then the formal result bolded, then accompanying findings}.
- **{Screening name} ({dd/mm/yyyy} — {radiologist}):** {findings;
  formal category bolded, e.g. **BI-RADS Category I (Normal)**}.
- **{DXA / BMD} ({dd/mm/yyyy} — {device}):** {verdict; one sub-item per
  site with BMD, T-score, Z-score}.

---

## 3. Hematology, Biochemistry & Clinical Pathology

### A. Longitudinal Complete Blood Count (CBC) & Peripheral Smear

{When a parameter appears on several dates, ONE comparative table:}

| Hematological Parameter | {Baseline ({dd/mm/yyyy})} | {Pre-Tx ({dd/mm/yyyy})} | Reference Interval | Clinical & Pathological Interpretation |
| --- | --- | --- | --- | --- |
| {Parameter name} | **{value}** | **{value}** | {interval} | {one-sentence interpretation} |

{One row per parameter; bold values that are out of range in BOTH date
columns. With a single collection date, drop the extra date columns.}

### B. Metabolic, Hepatic, Renal, Lipid & Urinalysis Profile ({dd/mm/yyyy})

| Investigation / Panel | Result | Reference Range | Clinical Significance |
| --- | --- | --- | --- |
| {Panel, combining related analytes into one row joined by "•", e.g. "Fasting Glucose / HbA1c / eAG"} | {values} | {intervals} | {significance — bold abnormal results} |

---

## 4. Surgical Hospitalization & Operative Summary ({admission date} – {discharge date})

**Admission & Preoperative Evaluation ({admission date}):** {one
paragraph — age, parity, LMP, admitting team, indication, preoperative
exam and workup, diet/anthropometry if recorded}.

**Operative Procedure Note — {procedure} ({surgery date})**

{Narrative paragraph 1: anesthesia, positioning, preparation, port
placement, pneumoperitoneum — devices and values verbatim.}

**Intraoperative Findings & Technique:** {Narrative paragraph 2 —
findings, step-by-step technique with device names, specimen handling
and HPE submission, closure, counts. End with transfer, recovery, and
discharge date/status, then bold the estimated blood loss sentence, e.g.
**Estimated blood loss was 200 mL**. Never split a sentence across
paragraphs; no process narration.}

---

## 5. Inpatient Medications & Post-Discharge Care Plan

| Phase | Medication | Dosage & Regimen | Route & Meal Timing |
| --- | --- | --- | --- |
| {Inpatient or Discharge} | {medicine name} | {dose, schedule, duration} | {route, meal relation} |

{One row per medication, in document order, inpatient first.}

> **Follow-Up & Emergency Warning Instructions:** {supplementation/diet
> continuation, review interval and location, pending reports, and the
> explicit emergency-care triggers with the emergency phone number and
> consultant contact — bold the emergency number and consultant}.

---

*Patient: {patient_name with honorific} (UHID: {uhid}) | Consolidated Medical Report*

---

## Rules

1. Use ONLY facts present in the parsed data. Copy values, units,
   dosages, grades, and names verbatim — never round or convert.
2. Keep section numbering consecutive after dropping empty sections.
3. Bold clinically significant values and findings exactly where the
   skeleton shows bolding.
4. Respond with the filled Markdown document ONLY — no code fences, no
   commentary.

## Parsed clinical data

{content}
