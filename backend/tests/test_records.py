"""Records CRUD + household scoping."""

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d1e480000000049454e44ae426082"
)


async def _create_member(client, name="Asha") -> str:
    resp = await client.post("/api/v1/members", json={"name": name})
    return resp.json()["id"]


async def _create_record(client, member_id: str, **overrides) -> dict:
    payload = {
        "record_type": "doctor_visit",
        "record_date": "2026-03-10",
        "diagnosis": "hypertension stage 1",
        "clinical_data": {"bp": "150/95", "advice": "reduce sodium"},
        "tags": ["cardiology", "followup"],
        **overrides,
    }
    resp = await client.post(f"/api/v1/members/{member_id}/records", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_get_record(auth_client):
    member_id = await _create_member(auth_client)
    record = await _create_record(auth_client, member_id)
    assert record["diagnosis"] == "hypertension stage 1"
    assert record["clinical_data"] == {"bp": "150/95", "advice": "reduce sodium"}
    assert record["tags"] == ["cardiology", "followup"]
    assert record["attachments"] == []

    got = await auth_client.get(f"/api/v1/members/{member_id}/records/{record['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == record["id"]


async def test_list_orders_desc_and_filters_by_type(auth_client):
    member_id = await _create_member(auth_client)
    await _create_record(auth_client, member_id, record_date="2026-01-01")
    await _create_record(auth_client, member_id, record_date="2026-06-01")
    lab = await _create_record(
        auth_client, member_id, record_type="lab_report", record_date="2026-03-01"
    )

    listing = (await auth_client.get(f"/api/v1/members/{member_id}/records")).json()
    assert [r["record_date"] for r in listing] == ["2026-06-01", "2026-03-01", "2026-01-01"]

    labs = (
        await auth_client.get(f"/api/v1/members/{member_id}/records?record_type=lab_report")
    ).json()
    assert [r["id"] for r in labs] == [lab["id"]]


async def test_update_and_soft_delete(auth_client):
    member_id = await _create_member(auth_client)
    record = await _create_record(auth_client, member_id)

    patched = await auth_client.patch(
        f"/api/v1/members/{member_id}/records/{record['id']}",
        json={"summary": "review in 3 months", "tags": ["cardiology"]},
    )
    assert patched.status_code == 200
    assert patched.json()["summary"] == "review in 3 months"
    assert patched.json()["tags"] == ["cardiology"]

    deleted = await auth_client.delete(f"/api/v1/members/{member_id}/records/{record['id']}")
    assert deleted.status_code == 204
    assert (
        await auth_client.get(f"/api/v1/members/{member_id}/records/{record['id']}")
    ).status_code == 404
    listing = (await auth_client.get(f"/api/v1/members/{member_id}/records")).json()
    assert listing == []


async def test_count_endpoint(auth_client):
    member_id = await _create_member(auth_client)
    await _create_record(auth_client, member_id)
    await _create_record(auth_client, member_id)
    resp = await auth_client.get(f"/api/v1/members/{member_id}/records/count/all")
    assert resp.json() == {"count": 2}


async def test_records_scoped_across_households(client):
    # user1 registers, creates member + record
    await client.post(
        "/api/v1/auth/register", json={"username": "owner1", "password": "Password1!"}
    )
    member_id = await _create_member(client)
    record = await _create_record(client, member_id)

    # user2 registers (cookie jar switches), must see neither
    await client.post(
        "/api/v1/auth/register", json={"username": "owner2", "password": "Password1!"}
    )
    assert (await client.get(f"/api/v1/members/{member_id}/records")).status_code == 404
    assert (
        await client.get(f"/api/v1/members/{member_id}/records/{record['id']}")
    ).status_code == 404


async def test_record_validation(auth_client):
    member_id = await _create_member(auth_client)
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records", json={"record_type": "doctor_visit"}
    )
    assert resp.status_code == 422  # record_date required
    resp = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={"record_type": "not_a_type", "record_date": "2026-01-01"},
    )
    assert resp.status_code == 422
