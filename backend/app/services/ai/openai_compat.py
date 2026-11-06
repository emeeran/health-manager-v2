"""OpenAI-compatible cloud provider (OpenAI, Groq, OpenRouter, ...)."""

import httpx

from app.core.config import get_settings
from app.services.ai.base import image_data_url


def _chat_capable(model: dict) -> bool:
    """True unless the catalogue entry declares itself non-chat (audio in,
    non-text out) or inactive. Entries without modality metadata qualify."""
    if model.get("active") is False:
        return False
    inputs = model.get("input_modalities")
    if inputs and "text" not in inputs:
        return False
    outputs = model.get("output_modalities")
    if outputs and "text" not in outputs:
        return False
    return True


class OpenAICompatibleProvider:
    local = False

    def __init__(self, name: str, api_key: str, base_url: str, model: str) -> None:
        self.name = name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = get_settings().EXTRACTION_PROVIDER_TIMEOUT

    async def available(self) -> bool:
        return bool(self.api_key)

    async def list_models(self) -> list[str]:
        """Live model catalogue (GET /models) for the model picker.

        Catalogues that carry modality metadata (e.g. Groq) are filtered to
        chat-capable entries — audio/speech/safety models reachable with the
        same key can't serve completions. Bare catalogues (OpenAI, etc.)
        pass through untouched."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
        return sorted(m["id"] for m in data if m.get("id") and _chat_capable(m))

    async def stream(self, prompt: str, *, system: str | None = None, max_tokens: int = 4096):
        """Yield text deltas via OpenAI-compatible SSE streaming."""
        import json
        from collections.abc import AsyncIterator

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async def _gen() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        if delta:
                            yield delta

        return _gen()

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: list[bytes] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if images:
            content: list[dict] = [
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url(img)},
                }
                for img in images
            ]
            content.append({"type": "text", "text": prompt})
            user_msg: dict = {"role": "user", "content": content}
        else:
            user_msg = {"role": "user", "content": prompt}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(user_msg)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"])
