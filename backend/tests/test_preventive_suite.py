"""Preventive-care rules: age/sex differences, conditions, vitals, dismissals."""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.condition import ConditionEpisode
from app.models.member import FamilyMember
from app.models.preventive import PreventiveDismissal  # noqa: F401 — registers tables
from app.models.vital import VitalMeasurement


async def _create_member(client, session_factory, **kwargs) -> str:
    sex = kwargs.pop("_sex", None)
    resp = await client.post("/api/v1/members", json={"name": "Asha", **kwargs})
    assert resp.status_code == 201, resp.text
    member_id = resp.json()["id"]
    if sex:
        async with session_factory() as db:
            member = await db.get(FamilyMember, uuid.UUID(member_id))
            member.sex = sex  # type: ignore[union-attr]
            await db.commit()
    return member_id


def _years_ago(n: int) -> date:
    today = date.today()
    try:
        return today.replace(year=today.year - n)
    except ValueError:  # Feb 29
        return today.replace(year=today.year - n, day=28)


async def _keys(client, member_id: str) -> set[str]:
    resp = await client.get(f"/api/v1/members/{member_id}/preventive")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert all(rec["due"] for rec in body["recommendations"])
    return {rec["key"] for rec in body["recommendations"]}


@pytest.mark.asyncio
async def test_young_child_gets_pediatric_rules(auth_client, session_factory):
    member_id = await _create_member(
        auth_client, session_factory, birth_date=str(_years_ago(3)), _sex="male"
    )
    keys = await _keys(auth_client, member_id)
    assert "well-child-visits" in keys
    assert "childhood-immunizations" in keys
    assert "annual-flu-vaccine" in keys
    # Adult rules must not fire for a 3-year-old.
    assert "annual-physical-exam" not in keys
    assert "lipid-profile" not in keys
    assert "breast-cancer-screening" not in keys
    assert "prostate-screening-discussion" not in keys


@pytest.mark.asyncio
async def test_adult_female_rules_differ_from_male(auth_client, session_factory):
    female_id = await _create_member(
        auth_client, session_factory, birth_date=str(_years_ago(55)), _sex="female"
    )
    male_id = await _create_member(
        auth_client, session_factory, birth_date=str(_years_ago(55)), _sex="male"
    )
    female = await _keys(auth_client, female_id)
    male = await _keys(auth_client, male_id)

    # Shared adult rules.
    for key in (
        "annual-physical-exam",
        "blood-pressure-screening",
        "colorectal-cancer-screening",
    ):
        assert key in female, f"female 55 missing {key}"
        assert key in male, f"male 55 missing {key}"
    assert "cervical-cancer-screening" in female
    assert "breast-cancer-screening" in female

    # Sex-specific rules.
    assert "breast-cancer-screening" not in male
    assert "cervical-cancer-screening" not in male
    assert "prostate-screening-discussion" in male
    assert "prostate-screening-discussion" not in female
    assert "well-child-visits" not in female


@pytest.mark.asyncio
async def test_member_without_birthdate_gets_no_age_rules(auth_client, session_factory):
    member_id = await _create_member(auth_client, session_factory)
    keys = await _keys(auth_client, member_id)
    assert keys == set()


@pytest.mark.asyncio
async def test_condition_rules_fire_on_episodes(auth_client, session_factory):
    member_id = await _create_member(auth_client, session_factory, birth_date=str(_years_ago(50)))
    async with session_factory() as db:
        db.add(
            ConditionEpisode(
                member_id=uuid.UUID(member_id),
                name="Type 2 Diabetes Mellitus",
                status="active",
            )
        )
        await db.commit()

    keys = await _keys(auth_client, member_id)
    assert "hba1c-test-every-3-months" in keys
    assert "diabetic-eye-exam" in keys
    assert "diabetic-foot-exam" in keys
    # A member without the condition never sees it.
    other_id = await _create_member(auth_client, session_factory, birth_date=str(_years_ago(50)))
    assert "hba1c-test-every-3-months" not in await _keys(auth_client, other_id)


@pytest.mark.asyncio
async def test_vitals_rule_high_blood_pressure(auth_client, session_factory):
    member_id = await _create_member(auth_client, session_factory, birth_date=str(_years_ago(50)))
    other_id = await _create_member(auth_client, session_factory, birth_date=str(_years_ago(50)))
    async with session_factory() as db:
        db.add(
            VitalMeasurement(
                member_id=uuid.UUID(member_id),
                vital_type="blood_pressure",
                value_num=150,
                value_secondary=95,
                unit="mmHg",
                measured_at=datetime.now() - timedelta(days=2),
            )
        )
        # Older, normal reading on the other member — no flag.
        db.add(
            VitalMeasurement(
                member_id=uuid.UUID(other_id),
                vital_type="blood_pressure",
                value_num=118,
                value_secondary=76,
                unit="mmHg",
                measured_at=datetime.now() - timedelta(days=2),
            )
        )
        await db.commit()

    assert "blood-pressure-recheck" in await _keys(auth_client, member_id)
    assert "blood-pressure-recheck" not in await _keys(auth_client, other_id)


@pytest.mark.asyncio
async def test_dismiss_undismiss_round_trip(auth_client, session_factory):
    member_id = await _create_member(auth_client, session_factory, birth_date=str(_years_ago(40)))
    key = "annual-physical-exam"

    assert key in await _keys(auth_client, member_id)

    dismissed = await auth_client.post(
        f"/api/v1/members/{member_id}/preventive/{key}/dismiss",
        json={"note": " travelling, will do on return"},
    )
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json() == {"key": key, "dismissed": True}
    assert key not in await _keys(auth_client, member_id)

    # Note is encrypted at rest.
    async with session_factory() as db:
        raw = await db.execute(
            text("SELECT note FROM preventive_dismissals WHERE rec_key = :k"),
            {"k": key},
        )
        stored = raw.scalar_one()
        assert stored.startswith("gAAAA")

    # Re-dismissing with no note is idempotent.
    again = await auth_client.post(f"/api/v1/members/{member_id}/preventive/{key}/dismiss")
    assert again.status_code == 200

    # Un-dismiss restores the recommendation.
    undone = await auth_client.delete(f"/api/v1/members/{member_id}/preventive/{key}/dismiss")
    assert undone.status_code == 204
    assert key in await _keys(auth_client, member_id)

    # A second un-dismiss has nothing to remove.
    assert (
        await auth_client.delete(f"/api/v1/members/{member_id}/preventive/{key}/dismiss")
    ).status_code == 404
