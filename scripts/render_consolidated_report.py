#!/usr/bin/env python3
"""Render extracted clinical_data JSON as a Consolidated Clinical Medical
Report — same layout as the Template JENY-MGM reference document.

Usage:
    uv run --project backend python scripts/render_consolidated_report.py \
        extraction.json [-o report.html]

The JSON is the app's extraction payload (clinical_data + summary). Output
is a self-contained HTML file; print it to PDF from any browser (A4, no
margins added by the @page rule beyond the template's own).
"""

import argparse
import html
import json
import sys
from datetime import date

TEAL_HEADER = "#1d4e5f"
TEAL_SECTION = "#16657d"
NAVY_TABLE = "#233b4d"
RED = "#c0392b"
GREEN = "#1e8e5a"


def esc(value) -> str:
    return html.escape(str(value)) if value not in (None, "") else ""


def _norm_name(name) -> str:
    """Loose family key: lowercase, drop digits/punctuation — collapses
    'Tab. Trapic (Tranexamic Acid) 500mg' and 'Tab. Trapic (Tranexamic acid)'."""
    import re

    return re.sub(r"[^a-z]+", "", str(name or "").lower())


def _full_date(value) -> str | None:
    iso = str(value or "")
    return iso if len(iso) == 10 and date.fromisoformat(iso) else None


def _dedupe(items, key_fn):
    seen = set()
    out = []
    for item in items:
        marker = key_fn(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _screening_family(s) -> str:
    text = str(s.get("type", "")).lower()
    for fam in ("pap", "mamm", "psa", "colon", "derm"):
        if fam in text:
            return fam
    return text


def flag_color(flag) -> str:
    if flag in ("low", "high", "critical"):
        return RED
    return "#1a1a1a"


def render(value, secondary, unit):
    parts = [esc(value)]
    if secondary not in (None, ""):
        parts.append(f"/ {esc(secondary)}")
    if unit not in (None, ""):
        parts.append(f" {esc(unit)}")
    return " ".join(parts)


def lab_table(labs, dates):
    """One row per parameter family, one column per collection date —
    entries for the same parameter (varied wording) merge into a single row."""
    families = {}
    for lab in labs:
        families.setdefault(_norm_name(lab.get("name")), []).append(lab)
    rows = []
    for family in families.values():
        display = sorted(family, key=lambda l: str(l.get("date") or ""))[0]
        cells = []
        for d in dates:
            entry = next(
                (l for l in family if str(l.get("date")) == d), None
            )
            if entry:
                color = flag_color(entry.get("flag"))
                cells.append(
                    f'<td class="val" style="color:{color}">'
                    f"{esc(entry.get('result'))} {esc(entry.get('units') or '')}</td>"
                )
            else:
                cells.append('<td class="val">—</td>')
        latest = sorted(
            family, key=lambda l: str(l.get("date") or "")
        )[-1]
        interp = {
            "low": "Below the standard reference interval.",
            "high": "Above the standard reference interval.",
            "normal": "Within the standard reference interval.",
        }.get(latest.get("flag") or "", "")
        rows.append(
            f"<tr><td class='param'>{esc(display.get('name'))}</td>{''.join(cells)}"
            f"<td class='ref'>{esc(latest.get('reference'))}</td>"
            f"<td class='interp'>{esc(interp)}</td></tr>"
        )
    date_cols = "".join(
        f"<th>{esc(fmt_date(d))}</th>" for d in dates
    )
    return (
        "<table class='labs'><thead><tr>"
        "<th>Parameter</th>" + date_cols +
        "<th>Standard Reference Interval</th><th>Clinical Interpretation</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def fmt_date(iso):
    try:
        return date.fromisoformat(str(iso)).strftime("%d %b %Y")
    except ValueError:
        return str(iso)


def render_report(data: dict) -> str:
    cd = data.get("clinical_data", data)
    patient = cd.get("patient") or {}
    labs = cd.get("labs") or []
    meds = cd.get("medications") or []
    imaging = cd.get("imaging") or []
    screenings = cd.get("screenings") or []
    vitals = cd.get("vitals") or []

    # Presentation normalization: only full ISO dates become comparison
    # columns; family-deduped rows keep the best-dated entry of each kind.
    labs = _dedupe(
        labs, lambda l: (_norm_name(l.get("name")), str(l.get("date")))
        if _full_date(l.get("date")) else (_norm_name(l.get("name")),)
    )
    lab_dates = sorted(
        {d for l in labs if (d := _full_date(l.get("date")))}
    )
    compared_names = {_norm_name(l.get("name")) for l in labs
                      if _full_date(l.get("date")) and l.get("reference")}
    comparison = [l for l in labs
                  if _norm_name(l.get("name")) in compared_names]
    # Family match by prefix so a bare "Hemoglobin" entry belongs to the
    # "Hemoglobin (Hb)" comparison row instead of leaking into the bullets.
    others = [l for l in labs
              if not any(
                  (n := _norm_name(l.get("name")))
                  and (n.startswith(cn) or cn.startswith(n))
                  for cn in compared_names
              )]

    meds = _dedupe(meds, lambda m: _norm_name(m.get("name")))
    screenings = _dedupe(screenings, _screening_family)

    vitals_line = " · ".join(
        render(v.get("value"), v.get("value_secondary"), v.get("unit"))
        for v in vitals
    )

    meds_html = "".join(
        f"<div class='med'><b>{i}. {esc(m.get('name'))}</b>"
        + (f" — {esc(m.get('dosage'))}" if m.get("dosage") else "")
        + (f"<br><i>Dosage: {esc(m.get('timing'))}."
           f" Target indication: {esc(m.get('indication'))}.</i></div>")
        for i, m in enumerate(meds, 1)
    )

    imaging_html = "".join(
        f"<p><b>{esc(i.get('modality', 'Study')).capitalize()} — {esc(i.get('region'))}"
        f"{' · ' + fmt_date(i.get('date')) if i.get('date') else ''}</b><br>"
        f"<b>Technique &amp; Findings:</b> {esc(i.get('findings'))}<br>"
        f"<b>Impression:</b> {esc(i.get('impression'))}</p>"
        for i in imaging
    )

    screening_html = ""
    for s in screenings:
        grade_color = GREEN if s.get("grade") else "#1a1a1a"
        screening_html += (
            f"<p><b>{esc(s.get('type'))}</b>"
            f"{' · ' + fmt_date(s.get('date')) if s.get('date') else ''}<br>"
            f"<b>Result:</b> {esc(s.get('result'))}<br>"
            + (f"<b>Final Impression: <span style='color:{grade_color}'>"
               f"{esc(s.get('grade'))}</span>.</b></p>"
               if s.get("grade") else "</p>")
        )
        result_text = str(s.get("result", "")).lower()
        if "dense" in result_text:
            screening_html += (
                "<div class='caveat'><i><b>Clinical Caveat:</b> Dense breast "
                "tissue inherently reduces the diagnostic sensitivity of "
                "X-rays and may obscure small underlying lesions. A "
                "supplementary screening breast ultrasound (USG) is "
                "routinely suggested for complete baseline "
                "correlation.</i></div>"
            )

    others_html = "".join(
        f"<li><b>{esc(l.get('name'))}:</b> "
        f"<span style='color:{flag_color(l.get('flag'))}'>{esc(l.get('result'))}"
        f" {esc(l.get('units') or '')}</span>"
        + (f" ({esc(l.get('reference'))})" if l.get("reference") else "")
        + ".</li>"
        for l in others
    )

    patient_name = esc(patient.get("name", "—"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Consolidated Clinical Medical Report — {patient_name}</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Segoe UI", Roboto, Arial, sans-serif; color: #1a1a1a;
         font-size: 10.5pt; line-height: 1.45; margin: 0; }}
  .page {{ max-width: 210mm; margin: 0 auto; padding: 24px 28px; }}
  .band {{ background: {TEAL_HEADER}; color: #fff; padding: 26px 30px; margin-bottom: 24px; }}
  .band h1 {{ margin: 0; font-size: 20pt; letter-spacing: 0.5px; }}
  .band p {{ margin: 6px 0 0; font-size: 9.5pt; color: #cfe0e6; letter-spacing: 2px;
            text-transform: uppercase; }}
  table.info {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  table.info td {{ border: 1px solid #d9e2e6; padding: 8px 12px; vertical-align: top; }}
  table.info td.label {{ background: #eef2f5; font-weight: 600; width: 16%;
                        color: {TEAL_HEADER}; }}
  h2 {{ color: {TEAL_SECTION}; font-size: 13.5pt; border-left: 4px solid {TEAL_SECTION};
       padding-left: 10px; margin: 26px 0 10px; }}
  h3 {{ color: {TEAL_SECTION}; font-size: 11pt; margin: 16px 0 6px; }}
  .box {{ background: #eef2f5; border-left: 4px solid {TEAL_HEADER};
         padding: 12px 16px; margin: 10px 0; }}
  .box h4 {{ margin: 0 0 8px; font-size: 10.5pt; }}
  .med {{ margin: 6px 0; }}
  .caveat {{ background: #f5f5f5; border-left: 4px solid #666; padding: 10px 14px;
            margin: 10px 0; font-size: 9.5pt; }}
  table.labs {{ width: 100%; border-collapse: collapse; margin: 10px 0 18px; }}
  table.labs th {{ background: {NAVY_TABLE}; color: #fff; padding: 8px 10px;
                  text-align: left; font-size: 9.5pt; }}
  table.labs td {{ border: 1px solid #d9e2e6; padding: 7px 10px; font-size: 9.5pt;
                  vertical-align: top; }}
  table.labs tr:nth-child(even) td {{ background: #f4f7f8; }}
  td.param {{ font-weight: 600; width: 20%; }}
  td.val {{ white-space: nowrap; }}
  td.ref {{ color: #444; }}
  ul {{ margin: 6px 0 12px 20px; padding: 0; }}
  li {{ margin: 4px 0; }}
  .footer {{ margin-top: 28px; padding-top: 8px; border-top: 1px solid #d9e2e6;
            display: flex; justify-content: space-between; color: #8a9aa2;
            font-size: 8.5pt; }}
</style>
</head>
<body>
<div class="page">
  <div class="band">
    <h1>CONSOLIDATED CLINICAL MEDICAL REPORT</h1>
    <p>Transcription &amp; Diagnostic Synthesis</p>
  </div>

  <table class="info">
    <tr>
      <td class="label">Patient Name</td><td>{patient_name}</td>
      <td class="label">UHID / Patient ID</td><td>{esc(patient.get('patient_id', '—'))}</td>
    </tr>
    <tr>
      <td class="label">Age / Sex</td><td>{esc(patient.get('age', '—'))} / {esc(patient.get('sex', '—'))}</td>
      <td class="label">Primary Facility</td><td>{esc(cd.get('facility', '—'))}</td>
    </tr>
    <tr>
      <td class="label">Consultant</td><td>{esc(cd.get('doctor_name', '—'))}</td>
      <td class="label">Report Compiled Date</td><td>{fmt_date(cd.get('record_date')) or '—'}</td>
    </tr>
    <tr>
      <td class="label">Clinical History</td><td colspan="3">{esc(cd.get('clinical_history', '—'))}</td>
    </tr>
  </table>

  <h2>1. Clinical Consultation &amp; Outpatient Prescription</h2>
  <p><b>Consultation Date:</b> {fmt_date(cd.get('record_date'))}</p>
  <p><b>Vitals:</b> {vitals_line or '—'}</p>
  <p><b>Physical Examination Findings:</b> {esc(cd.get('exam_findings', '—'))}</p>
  {f"<div class='box'><h4>Medical Management Plan &amp; Outpatient Prescription:</h4>{meds_html}</div>" if meds_html else ""}

  {f"<h2>2. Diagnostic Imaging</h2>{imaging_html}" if imaging_html else ""}

  {f"<h2>3. Preventive Cancer Screenings</h2>{screening_html}" if screening_html else ""}

  {f"<h2>4. Laboratory Investigations</h2><h3>A. Comparative Metrics</h3>{lab_table(comparison, lab_dates)}" if comparison else ""}
  {f"<h3>B. Additional Biochemical &amp; Metabolic Profiling</h3><ul>{others_html}</ul>" if others_html else ""}

  {f"<h2>5. Integrated Clinical Summary</h2><p>{esc(data.get('summary') or cd.get('summary'))}</p>" if (data.get('summary') or cd.get('summary')) else ""}

  <div class="footer">
    <span>Patient: {patient_name} | Case Summary Report</span>
    <span>Generated from structured extraction</span>
  </div>
</div>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()
    with open(args.json_path, encoding="utf-8") as fh:
        data = json.load(fh)
    html_out = render_report(data)
    out = args.out or args.json_path.rsplit(".", 1)[0] + "-report.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html_out)
    print(f"wrote {out}")
    if out.endswith(".html"):
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
