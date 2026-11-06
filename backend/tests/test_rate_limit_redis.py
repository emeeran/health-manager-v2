"""Redis-backed rate limiter: backend selection, sorted-set semantics via a
minimal in-process fake, and graceful fallback to memory on Redis failure.

No fakeredis — the fake below implements just the surface middleware.py
uses (pipeline(transaction=True) batching zadd/zremrangebyscore/zcard/
zrange/expire), which is also the contract a real Redis must honour.
"""

import sys
from collections import defaultdict

import httpx
import pytest


# ── Minimal async redis fake ──────────────────────────────────────────────


class FakeRedis:
    """In-process sorted sets with the handful of commands the limiter uses.
    ``now`` doubles as the limiter's clock so window expiry is testable."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now
        self.zsets: dict[str, dict[str, float]] = defaultdict(dict)
        self.ttls: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        return FakePipeline(self)

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.zsets[key].update(mapping)
        return len(mapping)

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        # Redis accepts "-inf"/"+inf"; coerce like a real server would.
        lo, hi = float(min_score), float(max_score)
        members = self.zsets.get(key, {})
        dead = [m for m, s in members.items() if lo <= s <= hi]
        for m in dead:
            del members[m]
        return len(dead)

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    async def zrange(
        self, key: str, start: int, stop: int, withscores: bool = False
    ) -> list[object]:
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: (kv[1], kv[0]))
        selected = items[start : stop + 1] if stop >= 0 else items[start:]
        return list(selected) if withscores else [m for m, _ in selected]

    def expire(self, key: str, seconds: int) -> int:
        self.ttls[key] = seconds
        return 1

    def tick(self, seconds: float) -> None:
        self.now += seconds


class FakePipeline:
    """Queues commands, runs them against the fake on execute() — the shape
    of redis-py's async Pipeline under MULTI."""

    def __init__(self, client: FakeRedis):
        self._client = client
        self._commands: list[tuple[str, tuple[object, ...]]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        self._commands.append(("zremrangebyscore", (key, min_score, max_score)))

    def zcard(self, key: str) -> None:
        self._commands.append(("zcard", (key,)))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._commands.append(("zadd", (key, mapping)))

    def expire(self, key: str, seconds: int) -> None:
        self._commands.append(("expire", (key, seconds)))

    async def execute(self) -> list[object]:
        return [getattr(self._client, name)(*args) for name, args in self._commands]


def _limiter(fake: FakeRedis, limit: int, window: float = 60.0):
    from app.core.middleware import RedisSlidingWindowRateLimiter

    return RedisSlidingWindowRateLimiter(
        "redis://localhost:6379/0",
        limit,
        window,
        client_factory=lambda _url: fake,
        clock=lambda: fake.now,
    )


# ── Backend selection ─────────────────────────────────────────────────────


@pytest.fixture
def mini_app_factory():
    from fastapi import FastAPI

    from app.core.middleware import configure_middleware

    def _make() -> FastAPI:
        app = FastAPI()
        configure_middleware(app, hsts=False)

        @app.get("/api/v1/ping")
        async def ping() -> dict:
            return {"ok": True}

        return app

    return _make


async def test_default_backend_is_memory_and_redis_never_imported(monkeypatch, mini_app_factory):
    monkeypatch.delenv("REDIS_URL", raising=False)
    sys.modules.pop("redis", None)  # drop any import from an earlier test
    app = mini_app_factory()
    from app.core.middleware import SlidingWindowRateLimiter

    assert app.state.rate_limit_backend == "memory"
    assert isinstance(app.state.general_rate_limiter, SlidingWindowRateLimiter)
    assert isinstance(app.state.auth_rate_limiter, SlidingWindowRateLimiter)
    assert "redis" not in sys.modules  # lazy import never triggered


async def test_redis_backend_selected_when_url_set(monkeypatch, mini_app_factory):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    sys.modules.pop("redis", None)
    app = mini_app_factory()
    from app.core.middleware import RedisSlidingWindowRateLimiter

    assert app.state.rate_limit_backend == "redis"
    assert isinstance(app.state.general_rate_limiter, RedisSlidingWindowRateLimiter)
    assert isinstance(app.state.auth_rate_limiter, RedisSlidingWindowRateLimiter)
    assert "redis" not in sys.modules  # client is lazy — nothing imported yet


# ── Sorted-set sliding-window semantics (against the fake) ────────────────


async def test_allows_up_to_limit_then_denies_with_retry_after():
    fake = FakeRedis()
    limiter = _limiter(fake, limit=3)
    for _ in range(3):
        allowed, retry_after = await limiter.check("ip:1.2.3.4")
        assert allowed and retry_after == 0
    allowed, retry_after = await limiter.check("ip:1.2.3.4")
    assert not allowed
    assert retry_after >= 1  # when the oldest hit drains out of the window


async def test_window_slides_hits_expire_and_expire_ttl_is_set():
    fake = FakeRedis()
    limiter = _limiter(fake, limit=2, window=60.0)
    for _ in range(2):
        allowed, _ra = await limiter.check("ip:1.2.3.4")
        assert allowed
    allowed, _ra = await limiter.check("ip:1.2.3.4")
    assert not allowed
    assert fake.ttls["ip:1.2.3.4"] == 60  # ZADD always rides with EXPIRE

    fake.tick(61)  # past the window: old hits prune out, a slot frees up
    allowed, retry_after = await limiter.check("ip:1.2.3.4")
    assert allowed and retry_after == 0
    assert fake.zcard("ip:1.2.3.4") == 1  # pruned, not accumulating


async def test_keys_are_independent():
    fake = FakeRedis()
    limiter = _limiter(fake, limit=1)
    allowed, _ra = await limiter.check("ip:1.1.1.1")
    assert allowed
    allowed, _ra = await limiter.check("ip:1.1.1.1")
    assert not allowed
    allowed, _ra = await limiter.check("auth:1.1.1.1")
    assert allowed  # untouched by the other key


# ── Graceful fallback ─────────────────────────────────────────────────────


async def test_falls_back_to_memory_when_redis_unreachable(monkeypatch):
    from fastapi import FastAPI

    from app.core.middleware import configure_middleware

    def _explode(_url: str) -> object:
        raise ConnectionError("redis down")

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr("app.core.middleware._create_redis_client", _explode)

    app = FastAPI()
    configure_middleware(app, hsts=False)

    @app.get("/api/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/ping")
        assert resp.status_code == 200  # never a 500
        assert app.state.rate_limit_backend == "memory-fallback"
        # Permanent for the process lifetime: still serving after the flip.
        resp = await c.get("/api/v1/ping")
        assert resp.status_code == 200
        assert app.state.rate_limit_backend == "memory-fallback"


async def test_fallen_back_limiter_enforces_memory_limits(monkeypatch):
    """The fallback is a real limiter, not a pass-through: limits still bite."""
    fake = FakeRedis()
    limiter = _limiter(fake, limit=1)
    limiter._client_factory = lambda _url: (_ for _ in ()).throw(ConnectionError("x"))
    allowed, _ra = await limiter.check("ip:1.1.1.1")  # fails over to memory window
    assert allowed
    allowed, _ra = await limiter.check("ip:1.1.1.1")
    assert not allowed


# ── In-memory regression (default path unchanged) ─────────────────────────


async def test_in_memory_default_still_rate_limits(monkeypatch, mini_app_factory):
    monkeypatch.delenv("REDIS_URL", raising=False)
    app = mini_app_factory()
    app.state.general_rate_limiter.limit = 2
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(2):
            assert (await c.get("/api/v1/ping")).status_code == 200
        resp = await c.get("/api/v1/ping")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert app.state.rate_limit_backend == "memory"
