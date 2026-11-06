"""Phase 8: runtime provider keys (app_secrets) — resolver, SSRF blocklist."""

import pytest

from app.services import provider_keys


@pytest.mark.asyncio
async def test_set_list_mask_delete(auth_client):
    put = await auth_client.put(
        "/api/v1/system/provider-keys/OPENAI_API_KEY",
        json={"value": "sk-super-secret-9876543210"},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["set"] is True
    assert body["source"] == "db"
    assert "sk-super-secret" not in body["value"]  # masked
    assert body["value"].endswith("3210")

    listed = (await auth_client.get("/api/v1/system/provider-keys")).json()["keys"]
    openai = next(k for k in listed if k["name"] == "OPENAI_API_KEY")
    assert openai["source"] == "db"
    assert "sk-super-secret" not in openai["value"]

    deleted = await auth_client.delete("/api/v1/system/provider-keys/OPENAI_API_KEY")
    assert deleted.status_code == 200
    assert deleted.json()["source"] == "none"

    again = await auth_client.delete("/api/v1/system/provider-keys/OPENAI_API_KEY")
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_stored_key_beats_env(auth_client, session_factory):
    # Settings default OLLAMA_MODEL=qwen3:4b; a stored override wins.
    put = await auth_client.put(
        "/api/v1/system/provider-keys/OLLAMA_MODEL", json={"value": "llama3:8b"}
    )
    assert put.status_code == 200

    async with session_factory() as session:
        resolved = await provider_keys.resolve_key(session, "OLLAMA_MODEL")
    assert resolved == "llama3:8b"
    from app.core.config import get_settings

    assert get_settings().OLLAMA_MODEL == "qwen3:4b"  # env untouched


@pytest.mark.asyncio
async def test_ssrf_blocklist(auth_client):
    for bad in (
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1",
    ):
        rejected = await auth_client.put(
            "/api/v1/system/provider-keys/OLLAMA_BASE_URL", json={"value": bad}
        )
        assert rejected.status_code == 422, bad

    # localhost Ollama stays allowed.
    ok = await auth_client.put(
        "/api/v1/system/provider-keys/OLLAMA_BASE_URL",
        json={"value": "http://localhost:11434"},
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_unknown_key_names_rejected(auth_client):
    assert (
        await auth_client.put("/api/v1/system/provider-keys/SECRET_MASTER_KEY", json={"value": "x"})
    ).status_code == 422


@pytest.mark.asyncio
async def test_admin_only(auth_client):
    from tests.test_household_admin import _extra_client

    async with _extra_client() as anon:
        assert (await anon.get("/api/v1/system/provider-keys")).status_code == 401
        assert (
            await anon.put("/api/v1/system/provider-keys/OPENAI_API_KEY", json={"value": "x"})
        ).status_code == 401


def test_mask_short_values():
    assert provider_keys.mask("") == ""
    assert provider_keys.mask("short") == "••••"
