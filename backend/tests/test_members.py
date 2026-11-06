async def test_create_and_list_members(auth_client):
    resp = await auth_client.post(
        "/api/v1/members",
        json={"name": "Asha", "relationship": "self", "birth_date": "1990-05-01"},
    )
    assert resp.status_code == 201, resp.text
    member = resp.json()
    assert member["name"] == "Asha"

    listing = await auth_client.get("/api/v1/members")
    assert listing.status_code == 200
    names = [m["name"] for m in listing.json()]
    assert names == ["Asha"]


async def test_member_validation(auth_client):
    resp = await auth_client.post("/api/v1/members", json={"relationship": "self"})
    assert resp.status_code == 422


async def test_get_update_delete_member(auth_client):
    member = (await auth_client.post("/api/v1/members", json={"name": "Ravi"})).json()

    got = await auth_client.get(f"/api/v1/members/{member['id']}")
    assert got.status_code == 200

    patched = await auth_client.patch(f"/api/v1/members/{member['id']}", json={"notes": "asthma"})
    assert patched.status_code == 200
    assert patched.json()["notes"] == "asthma"

    # sex drives the CDC growth-table series — round-trips through PATCH.
    sexed = await auth_client.patch(f"/api/v1/members/{member['id']}", json={"sex": "female"})
    assert sexed.status_code == 200
    assert sexed.json()["sex"] == "female"
    invalid = await auth_client.patch(f"/api/v1/members/{member['id']}", json={"sex": "dolphin"})
    assert invalid.status_code == 422

    deleted = await auth_client.delete(f"/api/v1/members/{member['id']}")
    assert deleted.status_code == 204
    assert (await auth_client.get(f"/api/v1/members/{member['id']}")).status_code == 404


async def test_members_scoped_per_user(client):
    await client.post("/api/v1/auth/register", json={"username": "user1", "password": "Password1!"})
    await client.post("/api/v1/members", json={"name": "User1 Member"})

    # Registering user2 overwrites the cookie jar -> second session.
    await client.post("/api/v1/auth/register", json={"username": "user2", "password": "Password1!"})
    resp = await client.get("/api/v1/members")
    assert resp.status_code == 200
    assert resp.json() == []  # user2 sees no members from user1's household


async def test_unknown_member_404(auth_client):
    import uuid

    resp = await auth_client.get(f"/api/v1/members/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_create_member_history_fields(auth_client):
    """Personal and family medical history are separate fields; unknown
    fields (e.g. the removed medications seeding) are rejected."""
    resp = await auth_client.post(
        "/api/v1/members",
        json={
            "name": "Asha",
            "relationship": "self",
            "medical_history": "Hypothyroidism",
            "family_medical_history": "Diabetes (mother)",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["medical_history"] == "Hypothyroidism"
    assert body["family_medical_history"] == "Diabetes (mother)"

    # No medications ride member creation anymore (pill-tracking cleanup) —
    # a legacy payload's medications key is ignored, not seeded.
    resp = await auth_client.post(
        "/api/v1/members",
        json={"name": "Asha 2", "medications": [{"medicine": "Metformin"}]},
    )
    assert resp.status_code == 201, resp.text
    meds = (await auth_client.get(f"/api/v1/members/{resp.json()['id']}/medications")).json()
    assert meds == []
