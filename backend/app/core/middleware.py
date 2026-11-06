"""Middleware stack — wired with a single ``configure_middleware(app)``.

Ports the v1 parity set: GZip, request-id echo, defensive security headers
(CSP / nosniff / referrer-policy / frame-options; HSTS only in production),
a tiered request-size limiter, and sliding-window rate limits (general +
stricter auth tier).

Deviations from v1, deliberate:
- Redis is opt-in via REDIS_URL (read from the env directly, like the other
  knobs here). Unset — the default — the limiter is purely in-memory and the
  redis package is never imported. Set, hits live in Redis sorted sets
  (one ZSET per key); if Redis is unreachable on first use the limiter logs
  a warning once and falls back to in-memory for the process lifetime
  (surfaced as rate_limit_backend="memory-fallback"). A Redis outage can
  never 500 a request.
- Limits and size caps come from the environment with v1's numbers as
  defaults (config.py is frozen this phase): RATE_LIMIT_GENERAL=100,
  RATE_LIMIT_AUTH=10, RATE_LIMIT_WINDOW_SECONDS=60, MAX_REQUEST_SIZE_MB=50,
  MAX_UPLOAD_SIZE_MB=500. Tests keep the limits effectively off by setting
  high values in tests/conftest.py; rate-limit behaviour itself is covered
  by test_ops_jobs.py against a mini app.
"""

import logging
import math
import os
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Awaitable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import env_int, get_settings

logger = logging.getLogger(__name__)


class TTLWindow:
    """One sliding-window hit counter per key, pruned lazily on read.

    In-memory by design (single process, no Redis). ``count`` drops
    timestamps older than the window before counting; ``record`` appends.
    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def count(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        window_start = now - self.window_seconds
        hits = self._hits[key]
        hits[:] = [ts for ts in hits if ts > window_start]
        return len(hits)

    def record(self, key: str, now: float | None = None) -> None:
        self._hits[key].append(time.monotonic() if now is None else now)
        self._prune_stale_keys()

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        hits = self._hits.get(key) or []
        if not hits:
            return 1
        oldest = min(hits)
        return max(1, int(oldest + self.window_seconds - now) + 1)

    def _prune_stale_keys(self) -> None:
        # Bound memory: drop fully-drained keys when the map grows large.
        if len(self._hits) > 10_000:
            now = time.monotonic()
            stale = [
                k
                for k, hits in self._hits.items()
                if not hits or max(hits) <= now - self.window_seconds
            ]
            for k in stale:
                self._hits.pop(k, None)


class SlidingWindowRateLimiter:
    """Sliding-window limiter over a :class:`TTLWindow`.

    ``limit`` is a plain attribute so tests (or runtime tuning) can lower or
    raise it without rebuilding the middleware.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = TTLWindow(window_seconds)

    async def check(self, key: str) -> tuple[bool, int]:
        """(allowed, retry_after_seconds). Records the hit when allowed."""
        if self.window.count(key) >= self.limit:
            return False, self.window.retry_after(key)
        self.window.record(key)
        return True, 0


def _create_redis_client(redis_url: str) -> Any:
    """Build the async redis client. Imported lazily so that a deployment
    without REDIS_URL never pays for (or even imports) the redis package."""
    import redis.asyncio as aioredis

    return aioredis.from_url(redis_url, decode_responses=True)


class RedisSlidingWindowRateLimiter:
    """Sliding-window limiter over Redis sorted sets — one ZSET per key.

    Scores are wall-clock timestamps (Redis is shared across processes, so
    ``time.monotonic()`` is meaningless there). Each check runs
    ZREMRANGEBYSCORE + ZCARD in one MULTI pipeline, and — when allowed —
    ZADD + EXPIRE in a second. The two pipelines are not jointly atomic,
    which is deliberate: a family-scale deployment tolerates the tiny
    over-admission race at burst time, and a denied request never consumes
    a slot. A Lua script would close the gap; not worth it here.

    Graceful degradation: the client is constructed on first use; any
    failure (missing package, connect, timeout, command error) flips
    ``backend`` to "memory-fallback", warns once, and permanently routes
    every later check through the in-memory limiter. A Redis outage can
    never 500 a request.
    """

    def __init__(
        self,
        redis_url: str,
        limit: int,
        window_seconds: float = 60.0,
        *,
        client_factory: Callable[[str], Any] | None = None,
        clock: Callable[[], float] = time.time,
        on_fallback: Callable[[], None] | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.backend = "redis"
        self._redis_url = redis_url
        self._client_factory = client_factory or _create_redis_client
        self._clock = clock
        self._on_fallback = on_fallback
        self._client: Any | None = None
        self._fallback = SlidingWindowRateLimiter(limit, window_seconds)
        self._warned = False

    async def check(self, key: str) -> tuple[bool, int]:
        if self.backend != "redis":
            return await self._fallback.check(key)
        try:
            return await self._check_redis(key)
        except Exception as exc:
            self.backend = "memory-fallback"
            if self._on_fallback is not None:
                self._on_fallback()
            if not self._warned:
                self._warned = True
                logger.warning(
                    "rate limiter: redis unavailable (%s) — falling back to "
                    "in-memory limits for the process lifetime",
                    exc,
                )
            return await self._fallback.check(key)

    async def _check_redis(self, key: str) -> tuple[bool, int]:
        client = self._client
        if client is None:
            client = self._client = self._client_factory(self._redis_url)
        now = self._clock()
        window_start = now - self.window_seconds

        async with client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            results = await pipe.execute()
        if int(results[1]) >= self.limit:
            oldest = await client.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(float(oldest[0][1]) + self.window_seconds - now) + 1)
            else:
                retry_after = 1
            return False, retry_after

        async with client.pipeline(transaction=True) as pipe:
            # Member must be unique per hit; the score is what counts.
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
            pipe.expire(key, max(1, math.ceil(self.window_seconds)))
            await pipe.execute()
        return True, 0


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Echo a unique X-Request-ID on every response, honoring an incoming one."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defensive headers on every response.

    CSP allows 'self' plus what the SPA needs: 'unsafe-inline' styles
    (Tailwind/React inline styles), data:/blob: images (thumbnails), and
    same-origin-only framing so the in-app document viewer keeps working
    while foreign sites can't embed us. HSTS only when ``hsts`` is set
    (production) — dev and desktop run plain http://localhost.
    """

    def __init__(self, app, *, hsts: bool = False):  # noqa: ANN001
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


# Health endpoints never rate-limit (load balancer probes are frequent).
_RATE_LIMIT_SKIP_PREFIXES = ("/api/v1/health", "/health", "/docs", "/openapi.json")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def _size_limit_bytes(path: str) -> int:
    """Tiered payload cap: uploads (extract/attachments/backup) get v1's 500MB,
    general API JSON 50MB."""
    if "/records/extract" in path or path.startswith("/api/v1/backup"):
        return env_int("MAX_UPLOAD_SIZE_MB", 500) * 1024 * 1024
    return env_int("MAX_REQUEST_SIZE_MB", 50) * 1024 * 1024


def configure_middleware(app: FastAPI, *, hsts: bool | None = None) -> None:
    """Install the full middleware stack on *app*.

    Order (add_middleware prepends, so the last-added runs first on the way
    out): gzip → size-limit+rate-limit → request-id → security headers,
    giving every response — including 429/413 — a request id and the
    defensive headers.
    """
    settings = get_settings()
    if hsts is None:
        hsts = settings.APP_ENV == "production"

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Rate limiters live on app.state so tests can retune limits in place.
    window = env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        # Redis backend; both tiers degrade together if Redis is unreachable.
        def _mark_fallback() -> None:
            app.state.rate_limit_backend = "memory-fallback"

        app.state.general_rate_limiter = RedisSlidingWindowRateLimiter(
            redis_url,
            env_int("RATE_LIMIT_GENERAL", 100),
            window,
            on_fallback=_mark_fallback,
        )
        app.state.auth_rate_limiter = RedisSlidingWindowRateLimiter(
            redis_url,
            env_int("RATE_LIMIT_AUTH", 10),
            window,
            on_fallback=_mark_fallback,
        )
        app.state.rate_limit_backend = "redis"
    else:
        app.state.general_rate_limiter = SlidingWindowRateLimiter(
            env_int("RATE_LIMIT_GENERAL", 100), window
        )
        app.state.auth_rate_limiter = SlidingWindowRateLimiter(
            env_int("RATE_LIMIT_AUTH", 10), window
        )
        app.state.rate_limit_backend = "memory"

    @app.middleware("http")
    async def size_limit_and_rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path.startswith(_RATE_LIMIT_SKIP_PREFIXES):
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                limit = _size_limit_bytes(path)
                if int(content_length) > limit:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "status_code": 413,
                            "error": "payload_too_large",
                            "message": (f"Request body exceeds {limit // (1024 * 1024)}MB limit"),
                        },
                    )
            except (ValueError, TypeError):
                pass

        ip = _client_ip(request)
        # Stricter tier for credential entrypoints — /auth/me keeps the
        # general limit (called on app load, not a brute-force target).
        limiter: SlidingWindowRateLimiter | RedisSlidingWindowRateLimiter
        key: str
        if path.startswith("/api/v1/auth/") and not path.startswith("/api/v1/auth/me"):
            limiter = request.app.state.auth_rate_limiter
            key = f"auth:{ip}"
        else:
            limiter = request.app.state.general_rate_limiter
            key = f"ip:{ip}"
        allowed, retry_after = await limiter.check(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "status_code": 429,
                    "error": "rate_limit_exceeded",
                    "message": "Rate limit exceeded. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=hsts)
