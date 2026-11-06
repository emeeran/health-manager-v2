"""Immunization schedule + catch-up calculator (Wave 6.2).

Rules encode India's Universal Immunisation Programme (UIP) — the app's
primary context — as data: one row per dose with a minimum age and a
minimum interval from the previous dose of the same antigen. The
catch-up math is then uniform:

    due_date = max(birth + min_age, prev_dose_date + min_interval)

Existing ``Vaccination`` rows match to doses by normalized-name
containment (the rows carry free-text names like "Hepatitis B" or
"Pentavalent 1"), first match wins in schedule order. Complete =
matched; overdue = due date in the past; due = within the next week;
upcoming = later. Interval catch-up for severely delayed series (the
ACIP-style "pick up where you left off, respect spacing" logic) IS this
rule set — spacing is enforced by the max() above, never back-dated.

Milestones: the WHO/IAHP-style screening checkpoints (social smile,
sitting, walking…) as static definitions; achievements persist per
member in ``milestone_achievements``.

Rule sources: the IAP-ACVIP Immunization Timetable 2025 (Indian
Pediatrics 2026;63:311-324, DOI 10.1007/s13312-026-00311-w) for the full
pediatric schedule, layered over India's UIP (MoHFW) which it includes
in modified form. Last verified against the published sources:
2026-11-04 — re-check when revising RULES.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

_MILESTONE_RE = re.compile(r"[^a-z0-9]+")


def _norm(name: str) -> str:
    return _MILESTONE_RE.sub("", (name or "").lower())


@dataclass(frozen=True)
class DoseRule:
    antigen: str  # grouping key ("DPT", "OPV"…)
    label: str  # human name ("DPT-1")
    match: tuple[str, ...]  # name fragments that identify a given dose
    min_age_days: int
    min_interval_days: int = 0  # from the previous dose of the same antigen


def _w(weeks: int) -> int:
    return weeks * 7


def _y(years: float) -> int:
    return int(years * 365.25)


# IAP-ACVIP 2025 layered over India's UIP. UIP doses keep their
# dose-numbered fragments (Pentavalent/OVP rows); the IAP-only antigens
# (influenza, typhoid, hepatitis A, varicella, HPV, Tdap, meningococcal,
# cholera) match generic brand/antigen fragments. Match fragments are
# lowercase-alphanumeric — _norm strips spaces/punctuation.
RULES: list[DoseRule] = [
    # Birth doses (UIP)
    DoseRule("BCG", "BCG", ("bcg",), 0),
    DoseRule("OPV", "OPV-0", ("opv0", "opv 0", "opv-0"), 0),
    DoseRule(
        "HEPB", "Hep-B birth", ("hepatitisbbirth", "hepbbirthdose", "hepbirth", "hepbn", "hepb0"), 0
    ),
    # 6-10-14 week primary series (UIP; pentavalent covers DTP/HepB/Hib)
    DoseRule("DPT", "DPT-1", ("dpt1", "pentavalent1", "penta1"), _w(6)),
    DoseRule("OPV", "OPV-1", ("opv1", "opv 1"), _w(6)),
    DoseRule("HEPB", "Hep-B 2", ("hepb2", "hepatitisb2", "hepatitisbsecond"), _w(6)),
    DoseRule("IPV", "IPV-1", ("ipv1", "ipv 1"), _w(6)),
    DoseRule("HIB", "Hib-1", ("hib1", "hib", "haemophilus", "hemophilus"), _w(6)),
    DoseRule("ROTA", "Rota-1", ("rota1", "rotavirus1", "rota", "rotavac", "rotavrix"), _w(6)),
    DoseRule("PCV", "PCV-1", ("pcv1", "pneumococcal1", "pcv", "pneumococcal"), _w(6)),
    DoseRule("DPT", "DPT-2", ("dpt2", "pentavalent2", "penta2"), _w(10), _w(4)),
    DoseRule("OPV", "OPV-2", ("opv2", "opv 2"), _w(10), _w(4)),
    DoseRule("HEPB", "Hep-B 3", ("hepb3", "hepatitisb3", "hepatitisbthird"), _w(10), _w(4)),
    DoseRule("IPV", "IPV-2", ("ipv2", "ipv 2"), _w(10), _w(4)),
    DoseRule("HIB", "Hib-2", ("hib2",), _w(10), _w(4)),
    DoseRule("ROTA", "Rota-2", ("rota2", "rotavirus2"), _w(10), _w(4)),
    DoseRule("PCV", "PCV-2", ("pcv2", "pneumococcal2"), _w(10), _w(4)),
    DoseRule("DPT", "DPT-3", ("dpt3", "pentavalent3", "penta3"), _w(14), _w(4)),
    DoseRule("OPV", "OPV-3", ("opv3", "opv 3"), _w(14), _w(4)),
    DoseRule("HEPB", "Hep-B 4", ("hepb4", "hepatitisb4"), _w(14), _w(4)),
    DoseRule("IPV", "IPV-3", ("ipv3", "ipv 3"), _w(14), _w(4)),
    DoseRule("HIB", "Hib-3", ("hib3",), _w(14), _w(4)),
    DoseRule("ROTA", "Rota-3", ("rota3", "rotavirus3"), _w(14), _w(4)),
    DoseRule("PCV", "PCV-3", ("pcv3", "pneumococcal3"), _w(14), _w(4)),
    # 9 months (UIP MR; IAP MMR-1)
    DoseRule("MR", "MR/MMR-1", ("mr1", "mmr1", "measles1"), _y(0.75)),  # 9 months
    DoseRule("JE", "JE-1 (endemic areas)", ("je1", "japaneseencephalitis1", "jev"), _y(0.75)),
    DoseRule(
        "MENACWY",
        "Meningococcal-1 (special situations)",
        ("meningococcal", "menacwy", "menactra", "menveo", "menfive"),
        _y(0.75),
    ),
    DoseRule("CHOLERA", "Cholera-1 (endemic areas)", ("cholera", "shanchol"), _y(0.75)),
    DoseRule("VITA", "Vitamin A-1", ("vitamina1",), _y(0.75)),
    # 6-12 months (IAP only)
    DoseRule("FLU", "Influenza-1 (6 months)", ("flu", "influenza", "iiv"), _y(0.5)),
    DoseRule(
        "TYPHOID",
        "Typhoid conjugate (single dose, 6-9 months)",
        ("typhoid", "tcv", "typbar", "typhbar"),
        _y(0.5),
    ),
    # 12 months (IAP only)
    DoseRule("HEPA", "Hepatitis A-1 (12 months)", ("hepatitisa", "hepa", "hav"), _y(1)),
    DoseRule(
        "MENACWY", "Meningococcal-2 (12 months)", ("meningococcal2", "menacwy2"), _y(1), _y(0.25)
    ),
    # 15 months (IAP only)
    DoseRule("MMR2", "MMR-2 (15 months)", ("mr2", "mmr2", "measles2"), 457, _w(4)),
    DoseRule("PCV", "PCV booster (15 months)", ("pcvbooster", "pneumococcalbooster"), 457),
    DoseRule(
        "VAR", "Varicella-1 (15 months)", ("varicella", "chickenpox", "varilrix", "okavax"), 457
    ),
    DoseRule("HIB", "Hib booster (16-18 months)", ("hibbooster", "hibb"), _y(1.4)),
    # 16-24 months (UIP + IAP boosters)
    DoseRule("DPT", "DPT booster-1", ("dptbooster1", "dptb1"), _y(1.25), _y(0.5)),
    DoseRule("OPV", "OPV booster", ("opvbooster",), _y(1.25)),
    DoseRule("IPV", "IPV booster-1", ("ipvbooster", "ipvb1"), _y(1.4)),
    DoseRule(
        "HEPA",
        "Hepatitis A-2 (18 months, inactivated vaccines)",
        ("hepatitisa2", "hepa2"),
        _y(1.5),
        _y(0.5),
    ),
    DoseRule("VAR", "Varicella-2 (18 months)", ("varicella2", "chickenpox2"), _y(1.5), 91),
    DoseRule("FLU", "Influenza-2 (7 months)", ("flu2", "influenza2"), 213, _w(4)),
    DoseRule(
        "FLU", "Influenza annual (till 5 years)", ("fluan", "influenzaan", "annualflu"), _y(1), 180
    ),
    DoseRule("JE", "JE-2 (endemic areas)", ("je2", "japaneseencephalitis2"), _y(1.25)),
    DoseRule("CHOLERA", "Cholera-2 (endemic areas)", ("cholera2",), _y(1.1)),
    # 4-6 years
    DoseRule("DPT", "DPT booster-2", ("dptbooster2", "dptb2"), _y(5), _y(3)),
    DoseRule("MMR3", "MMR-3 (4-6 years)", ("mmr3", "mr3", "measles3"), _y(5)),
    DoseRule("IPV", "IPV booster-2", ("ipvbooster2", "ipvb2"), _y(5)),
    # 10 years (IAP Tdap; UIP Td kept alongside)
    DoseRule("TDAP", "Tdap (10 years)", ("tdap", "boostrix", "adacel"), _y(10)),
    DoseRule("TT", "Td-1 (10y)", ("td1", "tt1", "tetanus10"), _y(10)),
    DoseRule("TT", "Td-2 (16y)", ("td2", "tt2", "tetanus16"), _y(16), _y(5)),
    # 9-14 years (IAP: single dose for girls, 2-dose for boys)
    DoseRule("HPV", "HPV-1 (9 years)", ("hpv", "gardasil", "cervavac", "humanpapilloma"), _y(9)),
    DoseRule("HPV", "HPV-2 (boys, 6 months after dose 1)", ("hpv2", "hpvdose2"), _y(9), 152),
]

MILESTONES: list[dict] = [
    {"key": "social_smile", "label": "Social smile", "age_months": 2},
    {"key": "head_steady", "label": "Head steady when held upright", "age_months": 3},
    {"key": "sits_unsupported", "label": "Sits without support", "age_months": 6},
    {"key": "babbles", "label": "Babbles ba-ba/da-da", "age_months": 6},
    {"key": "crawls", "label": "Crawls", "age_months": 9},
    {"key": "stands_with_help", "label": "Stands with support", "age_months": 9},
    {"key": "first_words", "label": "First words (mama/papa with meaning)", "age_months": 12},
    {"key": "walks", "label": "Walks a few steps", "age_months": 12},
    {"key": "walks_well", "label": "Walks well", "age_months": 15},
    {"key": "two_word_phrases", "label": "Two-word phrases", "age_months": 24},
    {"key": "runs", "label": "Runs", "age_months": 24},
    {"key": "speaks_sentences", "label": "Speaks short sentences", "age_months": 36},
    {"key": "hops", "label": "Hops on one foot", "age_months": 48},
]


def _match_given(name_norm: str, rule: DoseRule) -> bool:
    return any(fragment in name_norm for fragment in rule.match)


def build_schedule(
    dob: date, vaccinations: list[tuple[str, date]], today: date | None = None
) -> dict:
    """The dose-by-dose schedule with catch-up dates for one child.

    ``vaccinations``: (vaccine name, date administered) pairs from the
    Vaccination table. Pure — no DB.
    """
    run_date = today or date.today()
    given_norm = [(_norm(name), when) for name, when in vaccinations if when]
    last_of_antigen: dict[str, date] = {}
    doses: list[dict] = []

    for rule in RULES:
        prev = last_of_antigen.get(rule.antigen)
        from_birth = dob + timedelta(days=rule.min_age_days)
        from_prev = prev + timedelta(days=rule.min_interval_days) if prev else None
        due = max(from_birth, from_prev) if from_prev else from_birth

        matched_idx = next(
            (i for i, (name_norm, when) in enumerate(given_norm) if _match_given(name_norm, rule)),
            None,
        )
        matched = given_norm[matched_idx][1] if matched_idx is not None else None
        if matched_idx is not None:
            given_norm.pop(matched_idx)  # one row completes one dose
        if matched is not None:
            status = "complete"
            last_of_antigen[rule.antigen] = max(prev, matched) if prev else matched
        else:
            if due < run_date:
                status = "overdue"
            elif due <= run_date + timedelta(days=7):
                status = "due"
            else:
                status = "upcoming"
            # The catch-up clock advances from the *scheduled* date when a
            # dose isn't given — otherwise a delayed series never catches up.
            last_of_antigen[rule.antigen] = max(prev, due) if prev else due

        doses.append(
            {
                "antigen": rule.antigen,
                "label": rule.label,
                "due_date": due.isoformat(),
                "status": status,
                "given_date": matched.isoformat() if matched else None,
            }
        )

    overdue = sum(1 for d in doses if d["status"] == "overdue")
    return {
        "doses": doses,
        "summary": {
            "total": len(doses),
            "complete": sum(1 for d in doses if d["status"] == "complete"),
            "overdue": overdue,
        },
        "disclaimer": (
            "Schedule follows the IAP-ACVIP Immunization Timetable 2025 and "
            "India's Universal Immunisation Programme. Catch-up spacing is a "
            "minimum-interval guide — your pediatrician sets the actual plan."
        ),
    }


def milestones_for_age(age_months: float) -> list[dict]:
    """Static milestones annotated with expected status at ``age_months``."""
    out = []
    for m in MILESTONES:
        expected = "achieved" if age_months >= m["age_months"] else "upcoming"
        out.append({**m, "expected": expected})
    return out


def age_months_on(dob: date, on: date) -> float:
    """Age in months between two dates (the milestone convention)."""
    return (on - dob).days / 30.4375
