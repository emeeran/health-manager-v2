"""AI provider abstraction.

Providers implement `complete()` (text) and `complete_vision()` (prompt +
images). All HTTP is raw httpx — no SDKs. Providers must never raise for
"unavailable": they report `available` and the router skips them.
"""

import base64
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ExtractionResult:
    clinical_data: dict[str, Any]
    summary: str | None
    provider_used: str


@dataclass
class ProviderInfo:
    name: str
    available: bool
    local: bool
    model: str


class AIProvider(Protocol):
    name: str
    model: str
    local: bool
    timeout: int

    async def available(self) -> bool: ...

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: list[bytes] | None = None,
        max_tokens: int = 4096,
    ) -> str: ...


def image_data_url(data: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


@dataclass
class ProviderHealthCache:
    """Short-lived negative cache so dead providers don't add latency to
    every request. Deliberately simple: one TTL per provider name."""

    ttl_seconds: int = 60
    _state: dict[str, tuple[bool, float]] = field(default_factory=dict)

    def get(self, name: str, now: float) -> bool | None:
        entry = self._state.get(name)
        if entry is None or now - entry[1] > self.ttl_seconds:
            return None
        return entry[0]

    def set(self, name: str, ok: bool, now: float) -> None:
        self._state[name] = (ok, now)
