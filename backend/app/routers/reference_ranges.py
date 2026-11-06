"""Read-only guideline reference ranges (vitals + common labs) with citations.

Read-only public-health data (no PHI), but authenticated like every other
route. Every band carries a citation (source org / document / year / URL)
so any number on screen can be traced to its guideline.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.core.reference_ranges import all_ranges, bp_stage
from app.models import User

router = APIRouter(prefix="/reference-ranges", tags=["reference"])

_RANGE_SECTIONS = ("blood_pressure", "blood_glucose", "labs")


@router.get("")
async def get_reference_ranges(
    type: str | None = None, _: User = Depends(get_current_user)
) -> dict:
    """All guideline bands (or one section) with their full citations."""
    ranges = all_ranges()
    if type is None:
        return ranges
    if type not in _RANGE_SECTIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown reference section: {type}")
    return {type: ranges[type]}


@router.get("/bp-stage")
async def classify_bp(
    systolic: float, diastolic: float, _: User = Depends(get_current_user)
) -> dict:
    return bp_stage(systolic, diastolic)
