"""Health alerts: lab-anomaly alerts raised when extraction finds flags.

Deterministic rule (no AI): a lab result flagged ``low``/``high`` becomes
one HealthAlert. Severity is ``critical`` when the parsed numeric value is
at least 2x outside its numeric reference bounds, ``warning`` otherwise.
Duplicate suppression: one unacknowledged alert per (member, test, flag)
— re-extracting the same report never stacks alerts.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_alert import (
    ALERT_TYPE_LAB_ANOMALY,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    HealthAlert,
)

_CRITICAL_MULTIPLE = 2.0


def _lab_field(lab: dict, *names: str):
    for name in names:
        value = lab.get(name)
        if value not in (None, ""):
            return value
    return None


def _severity_for(lab: dict) -> str:
    value = lab.get("value_num")
    low = lab.get("ref_low_num")
    high = lab.get("ref_high_num")
    flag = lab.get("flag")
    if not isinstance(value, (int, float)):
        return SEVERITY_WARNING
    if flag == "high" and isinstance(high, (int, float)) and high > 0:
        return SEVERITY_CRITICAL if value >= high * _CRITICAL_MULTIPLE else SEVERITY_WARNING
    if flag == "low" and isinstance(low, (int, float)) and low > 0:
        return SEVERITY_CRITICAL if value <= low / _CRITICAL_MULTIPLE else SEVERITY_WARNING
    return SEVERITY_WARNING


async def create_alerts_for_labs(
    db: AsyncSession,
    member_id: uuid.UUID,
    record_id: uuid.UUID | None,
    labs: list[dict],
) -> list[HealthAlert]:
    """Create alerts for flagged labs; skips duplicates and normal flags.

    Accepts both extraction-shaped dicts (``name``/``reference``) and
    lab-result-shaped dicts (``test_name``/``ref_value``).
    """
    flagged = [
        lab for lab in labs or [] if isinstance(lab, dict) and lab.get("flag") in ("low", "high")
    ]
    if not flagged:
        return []

    existing = set(
        await db.scalars(
            select(HealthAlert.title).where(
                HealthAlert.member_id == member_id,
                HealthAlert.alert_type == ALERT_TYPE_LAB_ANOMALY,
                HealthAlert.acknowledged.is_(False),
            )
        )
    )

    created: list[HealthAlert] = []
    for lab in flagged:
        test_name = str(_lab_field(lab, "test_name", "name") or "Unknown test")
        title = f"{test_name} {lab['flag']}"
        if title in existing:
            continue
        existing.add(title)
        result = _lab_field(lab, "result", "value")
        units = _lab_field(lab, "units", "unit")
        reference = _lab_field(lab, "reference", "ref_value")
        message = (
            f"{test_name} is {lab['flag']}"
            + (f": {result}" if result is not None else "")
            + (f" {units}" if units else "")
            + (f" (reference: {reference})" if reference else "")
            + ". Discuss this result with a doctor."
        )
        alert = HealthAlert(
            member_id=member_id,
            record_id=record_id,
            alert_type=ALERT_TYPE_LAB_ANOMALY,
            severity=_severity_for(lab),
            title=title,
            message=message,
        )
        db.add(alert)
        created.append(alert)
    if created:
        await db.flush()
    return created


async def list_alerts(
    db: AsyncSession,
    member_id: uuid.UUID,
    unacknowledged_only: bool = False,
    limit: int = 100,
) -> list[HealthAlert]:
    filters = [HealthAlert.member_id == member_id]
    if unacknowledged_only:
        filters.append(HealthAlert.acknowledged.is_(False))
    return list(
        await db.scalars(
            select(HealthAlert).where(*filters).order_by(HealthAlert.created_at.desc()).limit(limit)
        )
    )


def alert_view(alert: HealthAlert) -> dict:
    return {
        "id": str(alert.id),
        "member_id": str(alert.member_id),
        "record_id": str(alert.record_id) if alert.record_id else None,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat(),
    }


async def acknowledge_alert(
    db: AsyncSession, member_id: uuid.UUID, alert_id: uuid.UUID
) -> HealthAlert:
    alert = await db.get(HealthAlert, alert_id)
    if alert is None or alert.member_id != member_id:
        raise LookupError("Alert not found")
    alert.acknowledged = True
    await db.flush()
    return alert
