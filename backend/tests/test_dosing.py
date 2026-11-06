"""Dosing engine unit tests — pure functions, no DB."""

from datetime import date

from app.services import dosing


def make_med(**overrides):
    from app.models import Medication

    defaults = {
        "member_id": None,
        "medicine": "Metformin",
        "medicine_key": "metformin",
        "status": "active",
        "schedule_type": "daily",
        "schedule_json": None,
        "start_date": date(2026, 1, 1),
    }
    return Medication(**{**defaults, **overrides})


class TestDaily:
    def test_daily_slots_expand(self):
        med = make_med(schedule_json='{"slots": ["morning", "bedtime"]}')
        doses = dosing.expand_day(med, date(2026, 5, 1))
        assert [d.slot for d in doses] == ["morning", "bedtime"]
        assert all(d.dose_count == 1 for d in doses)
        assert all(d.annotation is None for d in doses)
        assert doses[0].scheduled_time.hour == 8
        assert doses[1].scheduled_time.hour == 22

    def test_inactive_med_expands_empty(self):
        med = make_med(status="stopped", schedule_json='{"slots": ["morning"]}')
        assert dosing.expand_day(med, date(2026, 5, 1)) == []


class TestPrn:
    def test_prn_never_scheduled(self):
        med = make_med(schedule_type="prn", schedule_json="{}")
        assert dosing.expand_day(med, date(2026, 5, 1)) == []


class TestTaper:
    def test_taper_steps_down(self):
        med = make_med(
            schedule_type="taper",
            start_date=date(2026, 1, 1),
            schedule_json=(
                '{"slots": ["morning"], "doses_start": 3, "step": -1, '
                '"step_every_days": 7, "floor": 0}'
            ),
        )
        # Week 0 → 3 doses; week 1 → 2; week 2 → 1.
        assert dosing.expand_day(med, date(2026, 1, 3))[0].dose_count == 3
        assert dosing.expand_day(med, date(2026, 1, 10))[0].dose_count == 2
        assert dosing.expand_day(med, date(2026, 1, 17))[0].dose_count == 1

    def test_taper_annotation(self):
        med = make_med(
            schedule_type="taper",
            start_date=date(2026, 1, 1),
            schedule_json=(
                '{"slots": ["morning"], "doses_start": 3, "step": -1, '
                '"step_every_days": 7, "floor": 0}'
            ),
        )
        dose = dosing.expand_day(med, date(2026, 1, 2))[0]
        assert dose.annotation == "3 now — taper"
        single = dosing.expand_day(med, date(2026, 1, 17))[0]
        assert single.annotation is None  # no annotation when count is 1

    def test_finished_taper_drops_out(self):
        med = make_med(
            schedule_type="taper",
            start_date=date(2026, 1, 1),
            schedule_json=(
                '{"slots": ["morning"], "doses_start": 2, "step": -1, '
                '"step_every_days": 7, "floor": 0}'
            ),
        )
        # After 2 weeks: 2 - 2 = 0 → finished → no doses at all.
        assert dosing.expand_day(med, date(2026, 1, 15)) == []

    def test_taper_floor(self):
        med = make_med(
            schedule_type="taper",
            start_date=date(2026, 1, 1),
            schedule_json=(
                '{"slots": ["morning"], "doses_start": 3, "step": -1, '
                '"step_every_days": 7, "floor": 1}'
            ),
        )
        # Week 10 would be max(3 - 10, floor 1) = 1 — never below floor.
        assert dosing.expand_day(med, date(2026, 3, 12))[0].dose_count == 1


class TestCycle:
    def test_cycle_on_off_days(self):
        med = make_med(
            schedule_type="cycle",
            start_date=date(2026, 1, 1),
            schedule_json='{"slots": ["morning"], "on_days": 21, "off_days": 7}',
        )
        assert len(dosing.expand_day(med, date(2026, 1, 5))) == 1  # day 5: on
        assert len(dosing.expand_day(med, date(2026, 1, 21))) == 1  # day 21: on
        assert dosing.expand_day(med, date(2026, 1, 23)) == []  # day 23: off
        assert len(dosing.expand_day(med, date(2026, 1, 30))) == 1  # day 30: new cycle

    def test_is_cycle_off_day(self):
        med = make_med(
            schedule_type="cycle",
            start_date=date(2026, 1, 1),
            schedule_json='{"slots": ["morning"], "on_days": 21, "off_days": 7}',
        )
        assert dosing.is_cycle_off_day(med, date(2026, 1, 23)) is True
        assert dosing.is_cycle_off_day(med, date(2026, 1, 5)) is False

    def test_is_cycle_off_day_false_for_daily(self):
        med = make_med(schedule_json='{"slots": ["morning"]}')
        assert dosing.is_cycle_off_day(med, date(2026, 5, 1)) is False


class TestSlotTimeOverrides:
    """A medicine's own slot_times beat the household SLOT_TIMES defaults."""

    def test_override_changes_scheduled_time(self):
        med = make_med(
            schedule_json='{"slots": ["morning", "bedtime"],'
            ' "slot_times": {"morning": "09:15", "bedtime": "22:00"}}'
        )
        doses = dosing.expand_day(med, date(2026, 5, 1))
        assert doses[0].scheduled_time.hour == 9
        assert doses[0].scheduled_time.minute == 15
        assert doses[1].scheduled_time.hour == 22

    def test_slots_without_override_keep_defaults(self):
        med = make_med(
            schedule_json='{"slots": ["morning", "noon"], "slot_times": {"morning": "09:15"}}'
        )
        doses = dosing.expand_day(med, date(2026, 5, 1))
        assert doses[0].scheduled_time.hour == 9  # overridden
        assert doses[1].scheduled_time.hour == 13  # noon default 13:00
        assert doses[1].scheduled_time.minute == 0

    def test_garbage_override_falls_back(self):
        med = make_med(
            schedule_json='{"slots": ["morning"], "slot_times": {"morning": "not-a-time"}}'
        )
        doses = dosing.expand_day(med, date(2026, 5, 1))
        assert doses[0].scheduled_time.hour == 8

    def test_unknown_slot_still_skipped(self):
        med = make_med(schedule_json='{"slots": ["noon"], "slot_times": {"weird": "05:00"}}')
        doses = dosing.expand_day(med, date(2026, 5, 1))
        assert [d.slot for d in doses] == ["noon"]
        assert doses[0].scheduled_time.hour == 13
