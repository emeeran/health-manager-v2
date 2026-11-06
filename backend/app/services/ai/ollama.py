"""Local Ollama provider (/api/chat, OpenAI-ish but with image support)."""

import json

import httpx

from app.core.config import get_settings
from app.services.ai.base import image_data_url


class OllamaProvider:
    name = "ollama"
    local = True

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.OLLAMA_MODEL
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.timeout = settings.OLLAMA_TIMEOUT

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                models = resp.json().get("models", [])
                return any(m.get("name", "").startswith(self.model.split(":")[0]) for m in models)
        except (httpx.HTTPError, ValueError):
            return False

    async def list_models(self) -> list[str]:
        """Installed model tags for the settings board's model picker."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
        return sorted(m.get("name", "") for m in models if m.get("name"))

    async def stream(self, prompt: str, *, system: str | None = None, max_tokens: int = 4096):
        """Yield text deltas via Ollama's streaming /api/chat."""
        from collections.abc import AsyncIterator

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }

        async def _gen() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except ValueError:
                            continue
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            yield delta
                        if chunk.get("done"):
                            return

        return _gen()

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: list[bytes] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        # qwen3-style thinking models: soft-disable reasoning — it burns
        # num_predict tokens without improving structured JSON output.
        # (Deterministic hard-off via API "think": False isn't portable
        # across Ollama versions.)
        return await self._chat(
            prompt + "\n\n/no_think", system=system, images=images, max_tokens=max_tokens
        )

    async def _chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: list[bytes] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        content: dict = {"role": "user", "content": prompt}
        if images:
            content["images"] = [image_data_url(img) for img in images]
        messages.append(content)
        base_payload = {
            "model": self.model,
            "messages": messages,
            # Streamed even for complete(): this Ollama server stalls on
            # stream:false requests (observed 2026-11-04 — a 5-token reply
            # never returns), while streaming answers in under a second.
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        # Deterministic thinking-off for qwen3-style models — otherwise
        # "thinking" tokens consume the num_predict budget and the reply
        # content comes back empty. Servers older than the think API reject
        # the field, so the first attempt carries it and the second drops it.
        for extra in ({"think": False}, {}):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={**base_payload, **extra},
                ) as resp:
                    if resp.status_code == 400 and extra:
                        continue
                    resp.raise_for_status()
                    return await _collect_stream(resp)
        raise httpx.HTTPError("Ollama /api/chat rejected every payload variant")


async def _collect_stream(resp: httpx.Response) -> str:
    """Concatenate content deltas from a streamed /api/chat response."""
    collected: list[str] = []
    async for line in resp.aiter_lines():
        if not line.strip():
            continue
        try:
            chunk = json.loads(line)
        except ValueError:
            continue
        delta = chunk.get("message", {}).get("content", "")
        if delta:
            collected.append(delta)
        if chunk.get("done"):
            break
    return "".join(collected)
