"""Phase 7: 2FA, share links, backup/restore pipeline, chat SSE."""

import json

import pyotp

# ── 2FA ───────────────────────────────────────────────────────────────


async def test_2fa_full_lifecycle(client):
    await client.post("/api/v1/auth/register", json={"username": "twofa", "password": "Password1!"})
    setup = await client.post("/api/v1/auth/2fa/setup")
    assert setup.status_code == 200, setup.text
    body = setup.json()
    assert body["secret"] and body["qr_data_url"].startswith("data:image/png")
    assert len(body["backup_codes"]) == 8

    # Login now demands a code (account not yet enabled — secret exists).
    # TOTP codes aren't accepted until enabled, so main login still works
    # pre-confirmation:
    pre = await client.post(
        "/api/v1/auth/login", json={"username": "twofa", "password": "Password1!"}
    )
    assert pre.status_code == 200

    # Confirm with a live TOTP code → enabled.
    code = pyotp.TOTP(body["secret"]).now()
    verify = await client.post("/api/v1/auth/2fa/verify", json={"code": code})
    assert verify.status_code == 200, verify.text

    # Password alone no longer logs in → requires_2fa.
    login = await client.post(
        "/api/v1/auth/login", json={"username": "twofa", "password": "Password1!"}
    )
    assert login.status_code == 200
    assert login.json() == {"requires_2fa": True}
    assert "access_token" not in login.cookies

    # /auth/login/2fa with a live TOTP code completes.
    code = pyotp.TOTP(body["secret"]).now()
    done = await client.post(
        "/api/v1/auth/login/2fa",
        json={
            "username": "twofa",
            "password": "Password1!",
            "code": code,
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["username"] == "twofa"
    assert "access_token" in done.cookies

    # Wrong code rejected.
    bad = await client.post(
        "/api/v1/auth/login/2fa",
        json={"username": "twofa", "password": "Password1!", "code": "000000"},
    )
    assert bad.status_code == 401


async def test_2fa_backup_code_login_and_disable(client):
    await client.post(
        "/api/v1/auth/register", json={"username": "backup", "password": "Password1!"}
    )
    setup = (await client.post("/api/v1/auth/2fa/setup")).json()
    code = pyotp.TOTP(setup["secret"]).now()
    assert (await client.post("/api/v1/auth/2fa/verify", json={"code": code})).status_code == 200

    # Log in with a backup code via /auth/login (code field).
    backup_code = setup["backup_codes"][0]
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "backup", "password": "Password1!", "code": backup_code},
    )
    assert login.status_code == 200, login.text

    # Same backup code is single-use → now rejected.
    reuse = await client.post(
        "/api/v1/auth/login",
        json={"username": "backup", "password": "Password1!", "code": backup_code},
    )
    assert reuse.status_code == 401

    # Disable with a fresh TOTP code.
    code = pyotp.TOTP(setup["secret"]).now()
    off = await client.post("/api/v1/auth/2fa/disable", json={"code": code})
    assert off.status_code == 204
    plain = await client.post(
        "/api/v1/auth/login", json={"username": "backup", "password": "Password1!"}
    )
    assert plain.status_code == 200


# ── Share links ───────────────────────────────────────────────────────


async def test_share_link_public_access_and_expiry(auth_client):
    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    await auth_client.post(
        f"/api/v1/members/{member['id']}/medications",
        json={"medicine": "Metformin", "dosage": "500 mg"},
    )
    await auth_client.post(
        f"/api/v1/members/{member['id']}/labs",
        json={"test_name": "HbA1c", "result": "8.1", "units": "%", "flag": "high"},
    )

    created = (
        await auth_client.post(
            f"/api/v1/members/{member['id']}/share-links", json={"expires_days": 7}
        )
    ).json()
    token = created["token_shown_once"]

    # Public endpoint — no cookies needed.
    import httpx

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as anon:
        resp = await anon.get(f"/api/v1/public/share/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["member"]["name"] == "Asha"
        assert body["medications"][0]["medicine"] == "Metformin"
        # Labs are NOT part of the redacted emergency summary.
        assert "labs" not in body

        # Reuse of the token is fine (not single-use) — bad token 404s.
        bad = await anon.get(f"/api/v1/public/share/{'deadbeef' * 8}")
        assert bad.status_code == 404


async def test_share_link_revocation(auth_client):
    member = (await auth_client.post("/api/v1/members", json={"name": "Ravi"})).json()
    created = (
        await auth_client.post(f"/api/v1/members/{member['id']}/share-links", json={})
    ).json()
    links = (await auth_client.get(f"/api/v1/members/{member['id']}/share-links")).json()
    assert links[0]["revoked"] is False

    delete = await auth_client.delete(f"/api/v1/members/{member['id']}/share-links/{created['id']}")
    assert delete.status_code == 204

    import httpx

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as anon:
        resp = await anon.get(f"/api/v1/public/share/{created['token_shown_once']}")
    assert resp.status_code == 404


# ── Backup / restore ──────────────────────────────────────────────────


async def test_backup_create_list_download(auth_client, tmp_path, monkeypatch):
    from app.services import backup_service

    monkeypatch.setattr(backup_service, "BACKUPS_DIR", tmp_path)
    import app.routers.backup as backup_router

    monkeypatch.setattr(backup_router, "backup_service", backup_service)

    await auth_client.post("/api/v1/members", json={"name": "Asha"})
    created = await auth_client.post("/api/v1/backup/create")
    assert created.status_code == 200, created.text
    filename = created.json()["filename"]
    assert filename.startswith("backup_") and filename.endswith(".enc")

    listing = (await auth_client.get("/api/v1/backup/list")).json()
    assert [b["filename"] for b in listing] == [filename]

    download = await auth_client.get(f"/api/v1/backup/download/{filename}")
    assert download.status_code == 200
    # The endpoint serves the already-decrypted archive; validate directly.
    backup_service.validate_archive(download.content)

    # Traversal and unknown names rejected. (FastAPI normalizes "../" in
    # the URL before routing, so a traversal can surface as 404 too.)
    traversal = await auth_client.get("/api/v1/backup/download/../../etc/passwd")
    assert traversal.status_code in (400, 404)
    assert (
        await auth_client.get("/api/v1/backup/download/backup_20990101_000000.tar.gz.enc")
    ).status_code == 404


async def test_restore_request_and_script(tmp_path, monkeypatch):
    """The full privileged pipeline, env-overridden: app writes request →
    restore-archive.sh swaps the DB."""
    import os
    import subprocess
    import tarfile
    import io
    import sqlite3

    from app.core.encryption import encrypt_bytes
    from app.services import backup_service

    data_dir = tmp_path / "data"
    backups = data_dir / "backups"
    backups.mkdir(parents=True)

    # Live "old" DB + attachments.
    old_db = data_dir / "health.db"
    conn = sqlite3.connect(old_db)
    conn.execute("CREATE TABLE marker (v TEXT)")
    conn.execute("INSERT INTO marker VALUES ('old')")
    conn.commit()
    conn.close()
    att = data_dir / "attachments" / "files" / "ab"
    att.mkdir(parents=True)
    (att / "abc.txt").write_text("attachment-contents")

    # Build a backup containing a "new" DB + attachments, encrypted.
    new_db = tmp_path / "new.db"
    conn = sqlite3.connect(new_db)
    conn.execute("CREATE TABLE marker (v TEXT)")
    conn.execute("INSERT INTO marker VALUES ('new')")
    conn.commit()
    conn.close()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        raw = new_db.read_bytes()
        info = tarfile.TarInfo(name="health.db")
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
        att_tar = tarfile.TarInfo(name="attachments/files/ab/abc.txt")
        content = b"restored-attachment"
        att_tar.size = len(content)
        tar.addfile(att_tar, io.BytesIO(content))
    archive = backups / "backup_20260101_000000.tar.gz.enc"
    archive.write_bytes(encrypt_bytes(buf.getvalue()))

    # The app-side request (same validation the endpoint runs).
    monkeypatch.setattr(backup_service, "BACKUPS_DIR", backups)
    monkeypatch.setattr(backup_service, "RESTORE_REQUEST", data_dir / ".restore-request")
    backup_service.request_restore(archive.name)

    # Run the root pipeline unprivileged via env overrides.
    script = "/home/em/code/health-manager-v2/packaging/restore-archive.sh"
    # A real `systemctl <verb> <unit>` hits polkit (manage-units needs auth)
    # and pops an authentication dialog, so intercept it and record calls.
    shim_bin = tmp_path / "bin"
    shim_bin.mkdir()
    calls = tmp_path / "systemctl.calls"
    shim = shim_bin / "systemctl"
    shim.write_text(f'#!/bin/sh\necho "$*" >> "{calls}"\n')
    shim.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{shim_bin}:{os.environ['PATH']}",
        "DATA_DIR": str(data_dir),
        "APP_SVC": "not-a-real-service",
        "CADDY_SVC": "",
        "APP_USER": str(os.getuid()),
        "CONFIG_ENV": str(tmp_path / "config.env"),
    }
    from app.core.config import get_settings

    (tmp_path / "config.env").write_text(f"ENCRYPTION_KEY={get_settings().ENCRYPTION_KEY}\n")
    proc = subprocess.run(["bash", script], env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    # DB swapped, attachments restored, request consumed, result written.
    conn = sqlite3.connect(old_db)
    value = conn.execute("SELECT v FROM marker").fetchone()[0]
    conn.close()
    assert value == "new"
    assert (data_dir / "attachments" / "files" / "ab" / "abc.txt").read_text() == (
        "restored-attachment"
    )
    assert json.loads((data_dir / ".restore-result").read_text())["status"] == "ok"
    assert not (data_dir / ".restore-request").exists()
    # Service quiesced around the swap, and never prompting polkit.
    assert calls.read_text().splitlines() == [
        "--no-ask-password stop not-a-real-service",
        "--no-ask-password start not-a-real-service",
    ]

    # A traversal attempt must fail without touching anything.
    (data_dir / ".restore-request").write_text("../../etc/passwd\n")
    proc = subprocess.run(["bash", script], env=env, capture_output=True, text=True)
    assert proc.returncode != 0
    assert json.loads((data_dir / ".restore-result").read_text())["status"] == "failed"


# ── Chat ──────────────────────────────────────────────────────────────


class FakeChatProvider:
    name = "fake-chat"
    model = "fake"
    local = True
    timeout = 1

    async def available(self):
        return True

    async def complete(self, prompt, **kwargs):
        return "full reply"

    async def stream(self, prompt, **kwargs):
        async def gen():
            for word in ("grounded ", "reply ", "from ", "records"):
                yield word

        return gen()


async def test_chat_stream_persists_and_streams(auth_client, monkeypatch):
    from app.services.ai import router as ai_router

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    await auth_client.post(
        f"/api/v1/members/{member['id']}/medications",
        json={"medicine": "Metformin", "dosage": "500 mg"},
    )

    conversation = (
        await auth_client.post(
            "/api/v1/conversations",
            json={"member_id": member["id"], "title": "Consultation"},
        )
    ).json()

    provider = FakeChatProvider()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])
    import app.routers.conversations as conv_router

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    events = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "What do my records say about diabetes?"},
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    stages = [e["stage"] for e in events]
    assert stages[0] == "context"
    assert "streaming" in stages
    assert stages[-1] == "complete"
    streamed = "".join(e.get("delta", "") for e in events if e["stage"] == "streaming")
    assert streamed == "grounded reply from records"
    final = events[-1]["message"]
    assert final["role"] == "assistant"

    # Persisted: user + assistant messages readable via the API.
    messages = (
        await auth_client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]

    # Member context injection: the provider saw Metformin.
    # (FakeChatProvider ignores prompts, so verify via a recorded fake.)
    # — covered below by test_chat_injects_member_context.


async def test_chat_schedules_claim_audit(auth_client, monkeypatch):
    import uuid

    from app.services.ai import router as ai_router
    from app.services.ai import verification as verification_service
    import app.routers.conversations as conv_router

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    conversation = (
        await auth_client.post("/api/v1/conversations", json={"member_id": member["id"]})
    ).json()

    provider = FakeChatProvider()

    async def fake_plan(db, household_id, local_only=False):
        return [provider]

    monkeypatch.setattr(ai_router, "plan_for_household", fake_plan)

    captured: dict = {}

    async def fake_schedule(db, member_id, subject_type, narrative, verifier, **kwargs):
        captured.update(subject_type=subject_type, narrative=narrative, **kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(verification_service, "schedule_audit", fake_schedule)

    class FakeSettings:
        AI_VERIFICATION_ENABLED = True

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "hello"},
    ) as resp:
        assert resp.status_code == 200
        async for _ in resp.aiter_lines():
            pass

    assert captured["subject_type"] == "chat_message"
    assert captured["narrative"] == "grounded reply from records"


async def test_chat_injects_member_context(auth_client, monkeypatch):
    from app.services.ai import router as ai_router
    import app.routers.conversations as conv_router

    class RecordingProvider(FakeChatProvider):
        def __init__(self):
            self.prompts = []

        async def stream(self, prompt, **kwargs):
            self.prompts.append(prompt)

            async def gen():
                yield "ok"

            return gen()

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    await auth_client.post(
        f"/api/v1/members/{member['id']}/medications",
        json={"medicine": "Metformin", "dosage": "500 mg"},
    )
    conversation = (
        await auth_client.post("/api/v1/conversations", json={"member_id": member["id"]})
    ).json()

    provider = RecordingProvider()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [provider])

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "hello"},
    ) as resp:
        async for _ in resp.aiter_lines():
            pass

    assert "Metformin" in provider.prompts[0]
    assert "Asha" in provider.prompts[0]


async def test_conversation_scoped_per_household(client):
    await client.post(
        "/api/v1/auth/register", json={"username": "chat_a", "password": "Password1!"}
    )
    conv = (await client.post("/api/v1/conversations", json={})).json()
    await client.post(
        "/api/v1/auth/register", json={"username": "chat_b", "password": "Password1!"}
    )
    resp = await client.get(f"/api/v1/conversations/{conv['id']}/messages")
    assert resp.status_code == 404


async def test_chat_fails_over_when_first_provider_dies(auth_client, monkeypatch):
    """A provider whose key exists but requests fail (the placeholder-key
    case) is skipped mid-stream; the next provider answers instead."""
    import time

    from app.services.ai import router as ai_router
    import app.routers.conversations as conv_router

    class DeadKeyProvider:
        name = "dead-key"
        model = "m"
        local = False
        timeout = 1

        async def available(self):
            return True  # key present — availability cannot see it's dead

        async def stream(self, prompt, **kwargs):
            raise RuntimeError("401 unauthorized")

    member = (await auth_client.post("/api/v1/members", json={"name": "Asha"})).json()
    conversation = (
        await auth_client.post("/api/v1/conversations", json={"member_id": member["id"]})
    ).json()

    dead = DeadKeyProvider()
    working = FakeChatProvider()
    working.name = "fallback"
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [dead, working])
    monkeypatch.setattr(ai_router.health_cache, "_state", {})

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    events = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "hello"},
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    assert events[-1]["stage"] == "complete"
    assert "grounded reply from records" in events[-1]["message"]["content"]
    # The dead provider is negative-cached so later requests skip it.
    assert ai_router.health_cache.get("dead-key", time.monotonic()) is False

    messages = (
        await auth_client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]


async def test_chat_error_stage_when_all_providers_fail(auth_client, monkeypatch):
    from app.services.ai import router as ai_router
    import app.routers.conversations as conv_router

    class DeadKeyProvider:
        name = "dead-key"
        model = "m"
        local = False
        timeout = 1

        async def available(self):
            return True

        async def stream(self, prompt, **kwargs):
            raise RuntimeError("503 upstream")

    conversation = (await auth_client.post("/api/v1/conversations", json={})).json()
    monkeypatch.setattr(ai_router, "build_plan", lambda local_only=False: [DeadKeyProvider()])
    monkeypatch.setattr(ai_router.health_cache, "_state", {})

    class FakeSettings:
        AI_VERIFICATION_ENABLED = False

    monkeypatch.setattr(conv_router, "get_settings", lambda: FakeSettings())

    events = []
    async with auth_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation['id']}/messages/stream",
        json={"content": "hello"},
    ) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    assert events[-1]["stage"] == "error"
    messages = (
        await auth_client.get(f"/api/v1/conversations/{conversation['id']}/messages")
    ).json()
    # The user message persists (commit on success) but no assistant reply.
    assert [m["role"] for m in messages] == ["user"]
