"""Voice memo transcription tests.

The test venv has no faster-whisper (optional dependency), so the
unavailable paths assert the real 501/install-hint contract and the
success path monkeypatches the router's `transcribe` handle.
"""

import httpx
import pytest_asyncio
from fastapi import FastAPI
from unittest.mock import patch

from app.routers.voice_memos import INSTALL_HINT

MEMBER_PAYLOAD = {"name": "Voice Test", "relationship": "self"}


@pytest_asyncio.fixture
async def api_client(auth_client):
    """Scoped app with exactly the routers this feature needs.

    voice_memos is wired into app/main.py by the Phase 11 integration step;
    until then the tests mount it directly (same get_db override as the
    global fixture, auth cookie carried over from the registered user).
    """
    from app.core.database import SessionLocal, get_db
    from app.routers import auth as auth_router
    from app.routers import members as members_router
    from app.routers import voice_memos as voice_memos_router

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(members_router.router, prefix="/api/v1")
    app.include_router(voice_memos_router.router, prefix="/api/v1")

    async def _override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.cookies.update(auth_client.cookies)
        yield c


async def _member_id(client) -> str:
    resp = await client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_capabilities_reports_unavailable(api_client):
    with patch("app.routers.voice_memos.whisper_available", return_value=False):
        resp = await api_client.get("/api/v1/voice-memos/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["model_size"] is None


async def test_capabilities_reports_available(api_client):
    with (
        patch("app.routers.voice_memos.whisper_available", return_value=True),
        patch("app.routers.voice_memos.model_size", return_value="base"),
    ):
        resp = await api_client.get("/api/v1/voice-memos/capabilities")
    assert resp.status_code == 200
    assert resp.json() == {"available": True, "model_size": "base"}


async def test_transcribe_501_with_install_hint_when_whisper_absent(api_client):
    member_id = await _member_id(api_client)
    with patch("app.routers.voice_memos.whisper_available", return_value=False):
        resp = await api_client.post(
            f"/api/v1/members/{member_id}/voice-memos",
            files={"audio": ("memo.webm", b"\x1a\x45\xdf\xa3", "audio/webm")},
        )
    assert resp.status_code == 501
    body = resp.json()
    assert "faster-whisper" in body["detail"]
    assert body["install_hint"] == INSTALL_HINT


async def test_transcribe_success_with_fake_loader(api_client):
    member_id = await _member_id(api_client)
    canned = ("Blood pressure 128 over 82 today, took metformin as usual", 6.4)
    with (
        patch("app.routers.voice_memos.whisper_available", return_value=True),
        patch(
            "app.routers.voice_memos.transcribe",
            return_value=canned,
        ) as mock_t,
    ):
        resp = await api_client.post(
            f"/api/v1/members/{member_id}/voice-memos",
            files={"audio": ("memo.webm", b"fake-bytes", "audio/webm")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"].startswith("Blood pressure")
    assert body["duration_s"] == 6.4
    mock_t.assert_called_once()


async def test_transcribe_rejects_non_audio_and_empty(api_client):
    member_id = await _member_id(api_client)
    with patch("app.routers.voice_memos.whisper_available", return_value=True):
        resp = await api_client.post(
            f"/api/v1/members/{member_id}/voice-memos",
            files={"audio": ("notes.txt", b"not audio", "text/plain")},
        )
        assert resp.status_code == 415
        resp = await api_client.post(
            f"/api/v1/members/{member_id}/voice-memos",
            files={"audio": ("memo.webm", b"", "audio/webm")},
        )
        assert resp.status_code == 422


async def test_transcribe_requires_member_in_household(client, api_client):  # noqa
    """Another household's member id is invisible (404, not 403)."""
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "otheruser",
            "password": "OtherPass1!",
        },
    )
    assert other.status_code == 200
    resp = await client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    foreign_id = resp.json()["id"]
    resp = await api_client.post(
        f"/api/v1/members/{foreign_id}/voice-memos",
        files={"audio": ("memo.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 404
