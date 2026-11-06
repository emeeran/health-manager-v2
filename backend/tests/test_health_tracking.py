"""Vitals, labs, medications, adherence, reminders API tests."""

from datetime import date, datetime, timedelta


async def _member(client, name="Asha") -> str:
    return (await client.post("/api/v1/members", json={"name": name})).json()["id"]


# ── Vitals ────────────────────────────────────────────────────────────


async def test_vitals_crud_and_filtering(auth_client):
    member_id = await _member(auth_client)
    base = datetime(2026, 5, 1, 8, 0)
    for i, (sys_d, dia) in enumerate([(142, 95), (138, 90), (128, 84)]):
        resp = await auth_client.post(
            f"/api/v1/members/{member_id}/vitals",
            json={
                "vital_type": "blood_pressure",
                "value_num": sys_d,
                "value_secondary": dia,
                "unit": "mmHg",
                "measured_at": (base + timedelta(days=i)).isoformat(),
            },
        )
        assert resp.status_code == 201, resp.text
    await auth_client.post(
        f"/api/v1/members/{member_id}/vitals",
        json={
            "vital_type": "weight",
            "value_num": 72.5,
            "unit": "kg",
            "measured_at": base.isoformat(),
        },
    )

    listing = (await auth_client.get(f"/api/v1/members/{member_id}/vitals")).json()
    assert len(listing) == 4
    assert listing[0]["value_num"] == 128  # desc by measured_at

    bp = (
        await auth_client.get(f"/api/v1/members/{member_id}/vitals?vital_type=blood_pressure")
    ).json()
    assert len(bp) == 3
    assert bp[0]["value_secondary"] == 84

    since_filtered = (
        await auth_client.get(
            f"/api/v1/members/{member_id}/vitals?since={datetime(2026, 5, 3).isoformat()}"
        )
    ).json()
    assert len(since_filtered) == 1


async def test_vital_validation_and_delete(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/vitals",
        json={
            "vital_type": "not_a_type",
            "value_num": 1,
            "measured_at": datetime.now().isoformat(),
        },
    )
    assert resp.status_code == 422

    vital = (
        await auth_client.post(
            f"/api/v1/members/{member_id}/vitals",
            json={
                "vital_type": "weight",
                "value_num": 70,
                "measured_at": datetime.now().isoformat(),
            },
        )
    ).json()
    assert (
        await auth_client.delete(f"/api/v1/members/{member_id}/vitals/{vital['id']}")
    ).status_code == 204
    assert len((await auth_client.get(f"/api/v1/members/{member_id}/vitals")).json()) == 0


async def test_vitals_scoped_across_households(client):
    await client.post("/api/v1/auth/register", json={"username": "vit_a", "password": "Password1!"})
    member_id = await _member(client)
    # switch household
    await client.post("/api/v1/auth/register", json={"username": "vit_b", "password": "Password1!"})
    resp = await client.get(f"/api/v1/members/{member_id}/vitals")
    assert resp.status_code == 404


# ── Labs ──────────────────────────────────────────────────────────────


async def test_labs_crud(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/labs",
        json={
            "test_name": "Hemoglobin",
            "result": "9.8",
            "units": "g/dL",
            "ref_value": "12.0-15.5",
            "value_num": 9.8,
            "ref_low_num": 12.0,
            "ref_high_num": 15.5,
            "flag": "low",
            "record_date": "2026-03-14",
        },
    )
    assert resp.status_code == 201, resp.text
    lab = resp.json()
    assert lab["flag"] == "low"

    listing = (await auth_client.get(f"/api/v1/members/{member_id}/labs")).json()
    assert [row["test_name"] for row in listing] == ["Hemoglobin"]

    assert (
        await auth_client.delete(f"/api/v1/members/{member_id}/labs/{lab['id']}")
    ).status_code == 204


async def test_lab_flag_validation(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/labs",
        json={"test_name": "X", "flag": "extremely"},
    )
    assert resp.status_code == 422


# ── Medications + adherence ───────────────────────────────────────────


async def _create_med(client, member_id: str, **overrides) -> dict:
    payload = {
        "medicine": "Metformin",
        "dosage": "500 mg",
        "schedule_type": "daily",
        "slots": ["morning", "evening"],
        "start_date": date.today().isoformat(),
        **overrides,
    }
    resp = await client.post(f"/api/v1/members/{member_id}/medications", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_medication_slot_times_and_provider(auth_client):
    """Dose clock times persist into schedule_json; provider_name round-trips."""
    member_id = await _member(auth_client)
    med = await _create_med(
        auth_client,
        member_id,
        slots=["morning", "noon", "evening", "bedtime"],
        slot_times={
            "morning": "08:30",
            "noon": "13:00",
            "evening": "18:00",
            "bedtime": "21:30",
        },
        provider_name="Dr Mehta",
    )
    assert med["provider_name"] == "Dr Mehta"
    assert med["schedule_json"]["slots"] == ["morning", "noon", "evening", "bedtime"]
    assert med["schedule_json"]["slot_times"] == {
        "morning": "08:30",
        "noon": "13:00",
        "evening": "18:00",
        "bedtime": "21:30",
    }

    # The pillbox schedules at the medicine's own clock times, not the
    # household SLOT_TIMES defaults (morning default is 08:00).
    today = (await auth_client.get(f"/api/v1/members/{member_id}/adherence/today")).json()
    by_slot = {d["slot"]: d["scheduled_time"] for d in today["doses"]}
    assert by_slot["morning"].endswith("T08:30:00Z")
    assert by_slot["bedtime"].endswith("T21:30:00Z")


async def test_medication_slot_times_validation(auth_client):
    member_id = await _member(auth_client)
    for bad in (
        {"slot_times": {"noonish": "12:00"}},  # unknown slot
        {"slot_times": {"morning": "25:00"}},  # out of range
        {"slot_times": {"morning": "eight thirty"}},  # not HH:MM
    ):
        payload = {
            "medicine": "Metformin",
            "schedule_type": "daily",
            "slots": ["morning", "noon"],
            **bad,
        }
        resp = await auth_client.post(f"/api/v1/members/{member_id}/medications", json=payload)
        assert resp.status_code == 422, (bad, resp.text)


async def test_medication_update_widened_fields(auth_client):
    """The schedule table's per-row Edit can PATCH any displayed column."""
    member_id = await _member(auth_client)
    med = await _create_med(auth_client, member_id)
    resp = await auth_client.patch(
        f"/api/v1/members/{member_id}/medications/{med['id']}",
        json={
            "medicine": "Syndopa 110",
            "dose_form": "Tab",
            "dosage": "100 mg",
            "timing": "after food",
            "duration_days": 30,
            "provider_name": "Dr Sivarajan",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["medicine"] == "Syndopa 110"
    # Renaming recomputes the dedup key.
    assert body["medicine_key"] == "syndopa110"
    assert body["dose_form"] == "Tab"
    assert body["timing"] == "after food"
    assert body["duration_days"] == 30
    assert body["provider_name"] == "Dr Sivarajan"


async def test_medication_update_slots_preserve_schedule_params(auth_client):
    """Slot edits merge into schedule_json; taper/cycle params survive."""
    member_id = await _member(auth_client)
    med = await _create_med(
        auth_client,
        member_id,
        schedule_type="taper",
        slots=["morning"],
        taper={"doses_start": 3, "step": -1, "step_every_days": 7, "floor": 0},
    )
    resp = await auth_client.patch(
        f"/api/v1/members/{member_id}/medications/{med['id']}",
        json={"slots": ["morning", "noon"], "slot_times": {"noon": "13:00"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schedule_json"]["slots"] == ["morning", "noon"]
    assert body["schedule_json"]["slot_times"] == {"noon": "13:00"}
    assert body["schedule_json"]["doses_start"] == 3

    # Clearing slots back leaves valid JSON the adherence logic can parse.
    resp = await auth_client.patch(
        f"/api/v1/members/{member_id}/medications/{med['id']}",
        json={"slots": []},
    )
    assert resp.status_code == 200, resp.text
    assert "slots" not in resp.json()["schedule_json"]
    assert resp.json()["schedule_json"]["doses_start"] == 3


async def test_medication_update_slot_times_validation(auth_client):
    member_id = await _member(auth_client)
    med = await _create_med(auth_client, member_id)
    for bad in ({"slot_times": {"noonish": "12:00"}}, {"slot_times": {"noon": "25:00"}}):
        resp = await auth_client.patch(
            f"/api/v1/members/{member_id}/medications/{med['id']}", json=bad
        )
        assert resp.status_code == 422, (bad, resp.text)


async def test_medication_create_daily(auth_client):
    member_id = await _member(auth_client)
    med = await _create_med(auth_client, member_id)
    assert med["schedule_type"] == "daily"
    assert med["schedule_json"] == {"slots": ["morning", "evening"]}
    assert med["medicine_key"] == "metformin"
    assert med["status"] == "active"


async def test_medication_taper_and_cycle_params(auth_client):
    member_id = await _member(auth_client)
    taper = await _create_med(
        auth_client,
        member_id,
        medicine="Prednisone",
        schedule_type="taper",
        slots=["morning"],
        taper={"doses_start": 3, "step": -1, "step_every_days": 7, "floor": 0},
    )
    assert taper["schedule_json"]["doses_start"] == 3

    cycle = await _create_med(
        auth_client,
        member_id,
        medicine="Atovaquone",
        schedule_type="cycle",
        slots=["evening"],
        cycle={"on_days": 21, "off_days": 7},
    )
    assert cycle["schedule_json"]["on_days"] == 21

    # taper without params → 422
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/medications",
        json={"medicine": "X", "schedule_type": "taper", "slots": ["morning"]},
    )
    assert resp.status_code == 422


async def test_pillbox_today(auth_client):
    member_id = await _member(auth_client)
    await _create_med(auth_client, member_id)

    today = (await auth_client.get(f"/api/v1/members/{member_id}/adherence/today")).json()
    assert len(today["doses"]) == 2  # morning + evening
    assert {d["slot"] for d in today["doses"]} == {"morning", "evening"}


async def test_pillbox_prn_taper_cycle(auth_client):
    member_id = await _member(auth_client)
    await _create_med(auth_client, member_id, medicine="Tramadol", schedule_type="prn", slots=None)
    await _create_med(
        auth_client,
        member_id,
        medicine="Prednisone",
        schedule_type="taper",
        slots=["morning"],
        taper={"doses_start": 3, "step": -1, "step_every_days": 7, "floor": 0},
    )
    await _create_med(
        auth_client,
        member_id,
        medicine="Atovaquone",
        schedule_type="cycle",
        slots=["evening"],
        cycle={"on_days": 1, "off_days": 1},
        start_date=date.today().isoformat(),
    )

    today = (await auth_client.get(f"/api/v1/members/{member_id}/adherence/today")).json()
    assert len(today["prn"]) == 1
    assert today["prn"][0]["medicine"] == "Tramadol"

    taper_dose = next(d for d in today["doses"] if d["medicine"] == "Prednisone")
    assert taper_dose["dose_count"] == 3
    assert taper_dose["annotation"] == "3 now — taper"

    cycle_doses = [d for d in today["doses"] if d["medicine"] == "Atovaquone"]
    # on_days=1: phase (today - start) % 2 → 0 = on, 1 = off. Today = day 0 = on.
    assert len(cycle_doses) == 1


async def test_finished_taper_drops_out_of_pillbox(auth_client):
    member_id = await _member(auth_client)
    # Taper started 3 weeks ago: 2 - 3 = finished.
    await _create_med(
        auth_client,
        member_id,
        medicine="Prednisone",
        schedule_type="taper",
        slots=["morning"],
        taper={"doses_start": 2, "step": -1, "step_every_days": 7, "floor": 0},
        start_date=(date.today() - timedelta(days=21)).isoformat(),
    )
    today = (await auth_client.get(f"/api/v1/members/{member_id}/adherence/today")).json()
    assert all(d["medicine"] != "Prednisone" for d in today["doses"])


async def test_medication_stop_and_list_filter(auth_client):
    member_id = await _member(auth_client)
    med = await _create_med(auth_client, member_id)
    patched = await auth_client.patch(
        f"/api/v1/members/{member_id}/medications/{med['id']}",
        json={"status": "stopped"},
    )
    assert patched.json()["status"] == "stopped"

    active = (
        await auth_client.get(f"/api/v1/members/{member_id}/medications?status=active")
    ).json()
    assert active == []


# ── Reminders ─────────────────────────────────────────────────────────


async def test_reminders_crud(auth_client):
    member_id = await _member(auth_client)
    resp = await auth_client.post(
        "/api/v1/reminders",
        json={
            "title": "Refill metformin",
            "member_id": member_id,
            "remind_at": datetime(2026, 6, 1, 9, 0).isoformat(),
            "repeat": "monthly",
        },
    )
    assert resp.status_code == 201, resp.text
    reminder = resp.json()

    done = await auth_client.patch(f"/api/v1/reminders/{reminder['id']}", json={"done": True})
    assert done.json()["done"] is True

    listing = (await auth_client.get("/api/v1/reminders")).json()
    assert len(listing) == 1

    assert (await auth_client.delete(f"/api/v1/reminders/{reminder['id']}")).status_code == 204


async def test_reminder_scopes_member(auth_client, client):
    # A reminder referencing another household's member must 404/422.
    await client.post(
        "/api/v1/auth/register", json={"username": "rem_other", "password": "Password1!"}
    )
    other_member = await _member(client, "OtherMember")
    await client.post("/api/v1/auth/register", json={"username": "rem_a", "password": "Password1!"})
    resp = await client.post(
        "/api/v1/reminders",
        json={
            "title": "sneaky",
            "member_id": other_member,
            "remind_at": datetime.now().isoformat(),
        },
    )
    assert resp.status_code == 404


# ── Reference ranges ──────────────────────────────────────────────────


async def test_reference_ranges(auth_client):
    resp = await auth_client.get("/api/v1/reference-ranges")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["blood_pressure"]["bands"]) == 5
    assert body["blood_glucose"]["fasting"]["normal_high"] == 99
    assert "citation" in body["blood_pressure"]["bands"][0]

    stage = await auth_client.get("/api/v1/reference-ranges/bp-stage?systolic=145&diastolic=92")
    assert "Stage 2" in stage.json()["label"]


async def test_medication_dose_form_and_notes(auth_client):
    """v1-style dose form (Tab/Cap/...) and free-text notes round-trip."""
    member_id = await _member(auth_client)
    med = await _create_med(auth_client, member_id, dose_form="Tab", notes="after breakfast")
    assert med["dose_form"] == "Tab"
    assert med["notes"] == "after breakfast"
