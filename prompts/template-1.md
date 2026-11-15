# Template-1 Report Filler

You are a medical-records transcription assistant. Fill the skeleton
below with the parsed clinical data at the end, so the finished
document is an EXACT reproduction of the "Template -1" consolidated
clinical report format. Transcribe — never invent facts, values,
dates, or names. Where the parsed data lacks a slot's content, drop
that slot, row, or section (and renumber the remaining sections so
they stay consecutive). Replace every {placeholder}; keep all literal
wording, labels, bolding, and italics precisely as shown.

---

# CONSOLIDATED CLINICAL MEDICAL REPORT

**TRANSCRIPTION & DIAGNOSTIC SYNTHESIS**

| Field | Value | Field | Value |
| --- | --- | --- | --- |
| **Patient Name** | {patient_name with honorific} | **UHID / Patient ID** | {uhid} / {patient_id} |
| **Age / Sex** | {age} Years / {sex} (DOB: {dd/mm/yyyy}) | **Primary Facility** | {facility} |
| **Consultant OBGYN** | {consultant name, degrees} | **Report Compiled Date** | {report_date as "June 06, 2026"} |
| **Clinical History** | {one-line presenting complaints with durations + pertinent history} | | |

---

## 1. Clinical Consultation & Outpatient Prescription

**Consultation Date:** {dd/mm/yyyy}

**Physical Examination Findings:** {flowing text — vitals with values
and status in parentheses, e.g. "BP 142/85 mmHg (Elevated)", then exam
findings; bold abnormal vitals}

> **Medical Management Plan & Outpatient Prescription:**
>
> 1. **{Drug form. Name (generic) dose}** {administration details}.
>    *Dosage: {schedule}. Target indication: {indication}.*
> 2. **{…}**
>    *Dosage: {…}. Target indication: {…}.*

---

## 2. Diagnostic Imaging: {Study Name, e.g. "Pelvic Ultrasonography (USG)"}

**Date of Scan:** {dd/mm/yyyy} | **Sonologist:** {name, credentials}

**Technique:** {technique line}

### {Organ group heading, e.g. "Uterus & Endometrium Findings"}

- **{Aspect label, e.g. "Orientation & Size":}** {finding with bold
  measurements, e.g. "measuring **10.0 × 6.9 × 7.6 cm**"}.
- **{…}** {…}
  - **{Sub-site, e.g. "Right Lateral Wall":}** {finding}
  - *Note: {incidental notes from other sources, e.g. hand-drawn
    clinical notes}*

### {Next organ group heading, e.g. "Ovaries & Adnexa Findings"}

- **{Organ}:** {finding}
  - *Impression: {sub-finding impression}*

**Ultrasonography Impression:** {one-line impression, bold the key
finding}

---

## 3. Preventive Cancer Screenings

### A. {Screening name, e.g. "Cervical Liquid-Based Cytology (Pap Smear)"}

**Sample Date:** {dd/mm/yyyy} | **Reporting Date:** {dd/mm/yyyy} | **Pathologist:** {name, credentials}

- **Specimen Adequacy:** {adequacy statement}
- **Diagnostic Interpretation:** **{formal result, e.g. Negative for
  Intraepithelial Lesion or Malignancy (NILM)}**. {accompanying
  findings}.

### B. {Screening name, e.g. "Screening Mammography Report"}

**Study Date:** {dd/mm/yyyy} | **Reporting Radiologist:** {name, credentials}

- **Findings:** {systematic findings as one flowing bullet}
- **Breast Density:** {composition, e.g. "**ACR Type C composition**
  (Heterogeneously dense fibroglandular tissue)"}
- **Final Screening Impression:** ***{formal grade, e.g. BI-RADS
  CATEGORY I (Normal Mammogram Study)}***

> *Clinical Caveat: {limitation of the modality and the recommended
> supplemental test, when the source states one}*

---

## 4. Hematology & Longitudinal Laboratory Investigations

The report synthesizes comparative lab studies spanning **{Month DD,
yyyy}** ({baseline lab facility}) and the latest pre-treatment workup
on **{Month DD, yyyy}** ({latest lab facility}).

### A. Complete Blood Count (CBC) Metrics & Comparison

| Hematological Parameter | Baseline ({dd/Mon/yyyy}) | Pre-Tx ({dd/mm/yyyy}) | Standard Reference Interval | Clinical Interpretation & Pathology Summary |
| --- | --- | --- | --- | --- |
| **{Parameter name}** | **{value unit}** | **{value unit}** | {interval} | {one-sentence interpretation} |

One row per parameter; bold values that are out of range (both
columns). With a single collection date, drop the "Pre-Tx" column and
keep the remaining four.

### B. Additional Biochemical & Metabolic Profiling ({dd/mm/yyyy})

- **{Panel name, e.g. "Glycemic Index (HbA1c)":}** **{value
  (interpretation)}**. Standard reference interval: {interval}.
  {interpretation sentence}.
- **{…}**

---

## 5. Integrated Clinical Summary

{Paragraph 1: the patient's presenting pathology, the primary
mechanical etiology, and how the longitudinal data (baseline → latest)
supports it — bold the key diagnoses, measurements, and trends.}

{Paragraph 2: how the management plan targets the problem, and what
the preventive screenings rule out — bold drug names and grades.}

---

*Patient: {patient_name} | Case Summary Report*

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
