"""Test fixtures.

Env vars are set BEFORE app imports so Settings() picks them up. A temp-file
SQLite DB is shared session-wide; each test drops/recreates all tables.
Auth rides the httpx cookie jar.
"""

import base64
import os
import secrets
import tempfile

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(32))
# ENCRYPTION_KEY must be a valid Fernet key (44-char urlsafe base64).
os.environ.setdefault("ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
os.environ.setdefault("CMDT_ENABLED", "false")
os.environ.setdefault("ALLOW_REGISTRATION", "true")
# AI must never reach a real provider from tests: point Ollama at a
# closed port and FORCE cloud keys empty (env vars beat the developer's
# backend/.env, which may hold real keys).
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
# Same for the additional OpenAI-compatible slots (developer .env may hold
# real keys; tests must never see a cloud provider unless they patch one in).
for _provider in ("GEMINI", "COHERE", "DEEPSEEK", "MISTRAL", "OPENROUTER", "HUGGINGFACE"):
    os.environ[f"{_provider}_API_KEY"] = ""
# Web push off in tests even when the developer's .env has VAPID keys.
os.environ["WEB_PUSH_ENABLED"] = "false"
os.environ["WEB_PUSH_VAPID_PRIVATE_KEY"] = ""
os.environ["WEB_PUSH_VAPID_PUBLIC_KEY"] = ""
# RAG off by default in test suite (tests that check grounding monkeypatch it in).
os.environ["RAG_INDEX_PATH"] = "/tmp/non-existent-hmv2-test-rag.sqlite"
# Ops middleware: keep the suite under the rate limits (each test's requests
# share one client IP, so the real 100/10 caps would trip across tests).
# Rate-limit behaviour itself is tested in test_ops_jobs.py against a mini
# app whose limiters are retuned in place.
os.environ.setdefault("RATE_LIMIT_GENERAL", "1000000")
os.environ.setdefault("RATE_LIMIT_AUTH", "1000000")

_dbfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_dbfile.name}")

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.database import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def db_tables():
    from app import models  # noqa: F401

    # Fresh provider-health cache per test — it is module-global, and a
    # test exercising failover (a dead verifier key) must not leave that
    # provider marked unhealthy for every test that follows.
    from app.services.ai import router as ai_router

    ai_router.health_cache._state.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_tables):
    from app.core.database import SessionLocal
    from app.main import app

    async def _override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides.clear()
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client):
    """Client with a registered + logged-in user (cookie jar holds auth)."""
    register = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "TestPass1!"},
    )
    assert register.status_code == 200, register.text
    return client


@pytest.fixture
def session_factory():
    return async_sessionmaker(engine, expire_on_commit=False)
