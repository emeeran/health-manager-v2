"""Drug-interaction analysis across a member's active medications.

The medication snapshot (names + dosages) is built deterministically in code;
the AI provider is asked only for the pairwise interaction analysis, in
structured form. Results are parsed defensively — a chatty or malformed reply
yields an empty list, never an error.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import json_repair

from app.models.medication import Medication

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"minor", "moderate", "major", "contraindicated"}

# Clinical vocabulary → the UI's three-level scale (types/drug-interaction.ts).
_SEVERITY_MAP = {
    "minor": "low",
    "low": "low",
    "moderate": "moderate",
    "major": "high",
    "high": "high",
    "contraindicated": "high",
}

INTERACTION_PROMPT = """You are a clinical pharmacist reviewing a patient's active medications for drug-drug interactions.

Active medications (name | dosage):
{med_list}

Analyze every pair for interactions. Return ONLY a JSON array (no prose, no markdown fences) — one object per interacting pair, each with exactly these keys:
- "drugs": the names of the interacting medications, copied from the list above
- "interaction": one-sentence description of what happens when combined
- "severity": one of "minor", "moderate", "major", "contraindicated"
- "mechanism": brief pharmacologic mechanism
- "recommendation": what the patient/clinician should do

If no pairs interact, return [].
"""


@dataclass(frozen=True)
class MedSnapshot:
    """Deterministic picture of the member's active meds sent to the AI."""

    medicines: list[dict]

    @property
    def prompt_list(self) -> str:
        return "\n".join(f"- {m['medicine']} | {m['dosage']}" for m in self.medicines)


def build_snapshot(medications: list[Medication]) -> MedSnapshot:
    """Active meds → [{medicine, dosage}] — computed in code, no AI involved."""
    medicines = [
        {"medicine": med.medicine, "dosage": med.dosage or "unspecified"}
        for med in medications
        if med.status == "active"
    ]
    return MedSnapshot(medicines=medicines)


def parse_interactions(reply: str) -> list[dict]:
    """Parse an AI reply into interaction dicts matching the frontend's
    ``DrugInteraction`` contract (drugs/severity/description/recommendation).

    Tolerates markdown fences and trailing prose via json_repair; drops
    entries missing the required keys, maps the clinical severity vocabulary
    (minor/major/contraindicated) onto the UI's (low/moderate/high), and
    tags every row as an AI estimate.
    """
    if not reply or not reply.strip():
        return []
    try:
        parsed = json_repair.loads(reply.strip())
    except Exception:  # noqa: BLE001 — json_repair rarely raises, but be safe
        parsed = None
    if not isinstance(parsed, list):
        # Last resort: grab the outermost JSON array from a chatty reply.
        match = re.search(r"\[.*\]", reply, re.S)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except (ValueError, TypeError):
            return []
    out: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        description = item.get("interaction") or item.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        severity = _SEVERITY_MAP.get(str(item.get("severity") or "moderate").lower(), "moderate")
        raw_drugs = item.get("drugs")
        drugs = (
            [str(d).strip() for d in raw_drugs if str(d).strip()]
            if isinstance(raw_drugs, list)
            else []
        )
        out.append(
            {
                "drugs": drugs,
                "severity": severity,
                "description": description.strip(),
                "recommendation": str(item.get("recommendation") or "").strip(),
                "source": "ai",
            }
        )
    return out
