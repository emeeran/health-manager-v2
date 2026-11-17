"""Shared date arithmetic."""

from datetime import date


def age_years(birth_date: date | None, today: date | None = None) -> int | None:
    """Age in whole years from birth_date, or None when unknown."""
    if birth_date is None:
        return None
    if today is None:
        today = date.today()
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )
