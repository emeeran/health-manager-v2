"""Provider adapters over httpx.MockTransport — no network."""

import json

import httpx
import pytest

from app.services.ai.ollama import OllamaProvider
from app.services.ai.openai_compat import OpenAICompatibleProvider


# Captured at import, before any test patches httpx.AsyncClient.
_ORIGINAL_CLIENT_INIT = httpx.AsyncClient.__init__


@pytest.fixture
def mock_http(monkeypatch):
    """Route every httpx.AsyncClient through a MockTransport."""

    def _install(handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []
        transport = httpx.MockTransport(lambda request: (seen.append(request), handler(request))[1])

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            _ORIGINAL_CLIENT_INIT(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        return seen

    return _install


async def test_ollama_complete(mock_http, monkeypatch):
    """complete() streams internally (stream:false stalls on real servers)
    and disables thinking so the num_predict budget becomes reply text."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        assert request.url.path == "/api/chat"
        assert payload["model"] == "test-model"
        assert payload["stream"] is True
        assert payload.get("think") is False
        assert payload["options"]["num_predict"] == 128
        assert payload["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            text=('{"message":{"content":"hel"}}\n{"message":{"content":"lo"},"done":true}\n'),
        )

    mock_http(handler)
    from app.core.config import get_settings

    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    get_settings.cache_clear()
    try:
        provider = OllamaProvider()
        out = await provider.complete("prompt", system="be brief", max_tokens=128)
        assert out == "hello"
    finally:
        get_settings.cache_clear()


async def test_ollama_complete_falls_back_without_think(mock_http, monkeypatch):
    """Servers older than the think API 400 the field; complete() retries."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        if "think" in payload:
            return httpx.Response(400, json={"error": "think is not supported"})
        assert payload["stream"] is True
        return httpx.Response(200, text='{"message":{"content":"ok"},"done":true}\n')

    mock_http(handler)
    from app.core.config import get_settings

    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    get_settings.cache_clear()
    try:
        provider = OllamaProvider()
        assert await provider.complete("prompt") == "ok"
        assert "think" not in seen[-1]
    finally:
        get_settings.cache_clear()


async def test_ollama_complete_with_images(mock_http):
    seen = mock_http(
        lambda request: httpx.Response(
            200,
            text='{"message":{"content":"saw it"},"done":true}\n',
        )
    )
    provider = OllamaProvider()
    out = await provider.complete("what is this?", images=[b"\xff\xd8\xffjpg"])
    assert out == "saw it"
    payload = json.loads(seen[0].content)
    assert payload["messages"][0]["images"][0].startswith("data:image/jpeg;base64,")


async def test_ollama_available(monkeypatch, mock_http):
    monkeypatch.setattr(OllamaProvider, "base_url", "http://ollama.test", raising=False)
    provider = OllamaProvider()

    mock_http(
        lambda request: httpx.Response(
            200, json={"models": [{"name": "qwen3:4b"}, {"name": "llama3"}]}
        )
    )
    assert await provider.available() is True

    mock_http(lambda request: httpx.Response(200, json={"models": []}))
    assert await provider.available() is False


async def test_openai_compat_complete(mock_http):
    seen = mock_http(
        lambda request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "cloud says hi"}}]},
        )
    )
    provider = OpenAICompatibleProvider(
        "openai-test", "sk-test-key", "https://api.test/v1", "gpt-test"
    )
    out = await provider.complete("hi there")
    assert out == "cloud says hi"
    request = seen[0]
    assert request.headers["authorization"] == "Bearer sk-test-key"
    assert request.url.path == "/v1/chat/completions"
    payload = json.loads(request.content)
    assert payload["model"] == "gpt-test"


async def test_openai_compat_vision_payload(mock_http):
    seen = mock_http(
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    )
    provider = OpenAICompatibleProvider("openai-test", "sk", "https://api.test/v1", "gpt-test")
    await provider.complete("describe", images=[b"\xff\xd8\xffimg"])
    content = json.loads(seen[0].content)["messages"][0]["content"]
    assert isinstance(content, list)
    kinds = [part["type"] for part in content]
    assert kinds == ["image_url", "text"]
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_openai_compat_list_models_filters_non_chat(mock_http):
    """Catalogue metadata (when present) filters the picker to chat-capable
    models — audio/speech/safety rows share the key but can't serve
    completions; catalogues without metadata pass through untouched."""
    seen = mock_http(
        lambda request: httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "chat-model",
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                    },
                    {"id": "whisper", "input_modalities": ["audio"]},
                    {
                        "id": "orpheus",
                        "input_modalities": ["text"],
                        "output_modalities": ["speech"],
                    },
                    {"id": "retired", "active": False},
                    {"id": "bare-id"},  # no metadata: passes through
                ]
            },
        )
    )
    provider = OpenAICompatibleProvider("x", "sk-test", "https://api.test/v1", "m")
    assert await provider.list_models() == ["bare-id", "chat-model"]
    assert seen[0].headers["authorization"] == "Bearer sk-test"


async def test_openai_compat_available_needs_key():
    assert await OpenAICompatibleProvider("x", "", "https://api.test/v1", "m").available() is False
    assert await OpenAICompatibleProvider("x", "sk", "https://api.test/v1", "m").available() is True


async def test_plan_prefers_cloud_and_appends_local(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # Pin blank (don't delenv): the developer's .env may carry a real key.
    monkeypatch.setenv("GROQ_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.services.ai import router as ai_router

        plan = ai_router.build_plan()
        assert [p.name for p in plan] == ["openai", "ollama"]
        local_plan = ai_router.build_plan(local_only=True)
        assert [p.name for p in local_plan] == ["ollama"]
    finally:
        get_settings.cache_clear()


async def test_health_negative_cache():
    from app.services.ai.base import ProviderHealthCache

    cache = ProviderHealthCache(ttl_seconds=10)
    assert cache.get("ollama", now=0) is None
    cache.set("ollama", False, now=0)
    assert cache.get("ollama", now=5) is False
    assert cache.get("ollama", now=11) is None  # expired
