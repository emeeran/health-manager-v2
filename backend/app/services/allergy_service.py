"""Allergen–medication conflict check + allergy read helpers.

Flags active medications whose normalized name contains a known allergy
substance. Deliberately conservative: pure string matching — no drug-class
ontology (penicillin → amoxicillin needs a class map; see backlog).
Findings are decision-support hints for review, not certainties.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.allergy import Allergy
from app.models.medication import Medication

# Substances shorter than this only match exactly — "As" must not fire inside
# "Aspirin".
MIN_SUBSTRING_LEN = 5


def normalize_drug_name(name: str | None) -> str:
    """Canonical form for matching: lowercase, alphanumerics only."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _contains(needle: str, haystack: str) -> bool:
    if len(needle) < MIN_SUBSTRING_LEN:
        return needle == haystack
    return needle in haystack


def find_conflicts(allergies: list[dict], medications: list[dict]) -> list[dict]:
    """Match allergies against medications by normalized medicine name.

    allergies: [{substance, severity}]; medications: [{medicine}].

    Returns [{allergy, severity, medication, matched_on}] where matched_on
    is "medicine_name".
    """
    conflicts: list[dict] = []
    for allergy in allergies:
        substance = normalize_drug_name(str(allergy.get("substance", "")))
        if not substance:
            continue
        severity = allergy.get("severity") or "mild"
        for med in medications:
            med_name = normalize_drug_name(str(med.get("medicine", "")))
            if med_name and _contains(substance, med_name):
                conflicts.append(
                    {
                        "allergy": allergy.get("substance", ""),
                        "severity": severity,
                        "medication": med.get("medicine", ""),
                        "matched_on": "medicine_name",
                    }
                )
    return conflicts


async def check_member_conflicts(db: AsyncSession, member_id: uuid.UUID) -> list[dict]:
    """Load a member's allergies + active medications and return conflicts."""
    allergy_rows = list(await db.scalars(select(Allergy).where(Allergy.member_id == member_id)))
    med_rows = list(
        await db.scalars(
            select(Medication).where(
                Medication.member_id == member_id,
                Medication.status == "active",
            )
        )
    )
    if not allergy_rows or not med_rows:
        return []

    allergies = [{"substance": a.substance, "severity": a.severity} for a in allergy_rows]
    medications = [{"medicine": m.medicine} for m in med_rows]
    return find_conflicts(allergies, medications)


async def list_for_member(db: AsyncSession, member_id: uuid.UUID) -> list[Allergy]:
    return list(
        await db.scalars(
            select(Allergy).where(Allergy.member_id == member_id).order_by(Allergy.created_at.asc())
        )
    )


async def count_for_member(db: AsyncSession, member_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(Allergy).where(Allergy.member_id == member_id)
        )
        or 0
    )
