async def test_register_login_me(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "Password1!", "household_name": "A"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_register_duplicate_username(client):
    payload = {"username": "bob", "password": "Password1!"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 200
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


async def test_register_validation(client):
    resp = await client.post("/api/v1/auth/register", json={"username": "x", "password": "short"})
    assert resp.status_code == 422


async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={"username": "carol", "password": "Password1!"})
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "carol", "password": "wrong-pass"}
    )
    assert resp.status_code == 401


async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_refresh_rotates_and_old_token_is_single_use(client):
    await client.post("/api/v1/auth/register", json={"username": "dave", "password": "Password1!"})
    refresh_cookie = client.cookies.get("refresh_token")
    assert refresh_cookie

    first = await client.post("/api/v1/auth/refresh")
    assert first.status_code == 200, first.text

    # Old refresh cookie value must be single-use: replay it from a clean jar.
    import httpx

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as replay_client:
        replay_client.cookies.set("refresh_token", refresh_cookie)
        replay = await replay_client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401


async def test_logout_revokes_session(client):
    await client.post("/api/v1/auth/register", json={"username": "erin", "password": "Password1!"})
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_bearer_fallback(client):
    await client.post("/api/v1/auth/register", json={"username": "frank", "password": "Password1!"})
    token = client.cookies.get("access_token")
    client.cookies.clear()
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
