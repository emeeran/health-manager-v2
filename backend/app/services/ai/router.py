"""Provider selection and failover.

Plan = ordered provider list. Cloud-first when any cloud key is configured,
Ollama as the fallback tail. `member.cloud_ai_consent is False` forces a
local-only plan — PHI must never egress to cloud providers.

`build_plan` is module-level precisely so tests can patch it
(`monkeypatch.setattr(ai_router, "build_plan", ...)`).
"""

import time

from app.core.config import get_settings
from app.services.ai.base import AIProvider, ProviderHealthCache, ProviderInfo
from app.services.ai.ollama import OllamaProvider
from app.services.ai.openai_compat import OpenAICompatibleProvider

_health = ProviderHealthCache()

# Public alias: the scheduler's check_ai_providers job feeds its probe
# results into this cache so the router's circuit breaker reflects them.
health_cache = _health


def _cloud_specs() -> list[tuple[str, str, str, str]]:
    settings = get_settings()
    specs = []
    if settings.OPENAI_API_KEY:
        specs.append(
            ("openai", settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL, settings.OPENAI_MODEL)
        )
    if settings.GROQ_API_KEY:
        specs.append(("groq", settings.GROQ_API_KEY, settings.GROQ_BASE_URL, settings.GROQ_MODEL))
    for name in (
        "GEMINI",
        "COHERE",
        "DEEPSEEK",
        "MISTRAL",
        "OPENROUTER",
        "HUGGINGFACE",
    ):
        api_key = getattr(settings, f"{name}_API_KEY")
        if api_key:
            specs.append(
                (
                    name.lower(),
                    api_key,
                    getattr(settings, f"{name}_BASE_URL"),
                    getattr(settings, f"{name}_MODEL"),
                )
            )
    return specs


def build_plan(local_only: bool = False) -> list:
    cloud = [OpenAICompatibleProvider(*spec) for spec in _cloud_specs()]
    local = [OllamaProvider()]
    if local_only:
        return local
    return cloud + local if cloud else local


async def plan_for_household(db, household_id, local_only: bool = False) -> list:
    """Household-aware plan: per-provider enable/model/base_url overrides from
    households.settings_json layered over the env-derived plan.

    primary_provider=local forces local-only (PHI stays on-box). A config
    that disables every resolved provider falls back to the env plan rather
    than leaving the household with no provider at all.
    """
    import json

    from app.models import Household

    household = await db.get(Household, household_id)
    cfg: dict = {}
    if household is not None and household.settings_json:
        try:
            parsed = json.loads(household.settings_json)
            if isinstance(parsed, dict):
                cfg = parsed
        except ValueError:
            pass

    primary = cfg.get("primary_provider")
    if primary == "local":
        local_only = True
    plan = build_plan(local_only=local_only)

    # Stored credentials (Settings → AI providers → Credentials) beat the
    # env-derived defaults; household overrides below beat both. Keys with
    # no env-derived slot still become providers — a desktop install has
    # no shell env, so stored keys are its only cloud configuration.
    from app.services.provider_keys import apply_stored_credentials, expand_plan_with_stored

    if not local_only:
        plan = await expand_plan_with_stored(db, plan)
    await apply_stored_credentials(db, plan)

    # Named primary (e.g. "groq"): float it to the front of the failover
    # order. If it isn't configured it simply stays out of the way.
    if primary not in (None, "auto", "cloud", "local"):
        plan.sort(key=lambda p: p.name != primary)

    overrides = {p.get("name"): p for p in cfg.get("providers", []) if isinstance(p, dict)}
    resolved: list = []
    for provider in plan:
        override = overrides.get(provider.name, {})
        if override.get("enabled") is False:
            continue
        if override.get("model"):
            provider.model = override["model"]
        if override.get("base_url"):
            provider.base_url = override["base_url"].rstrip("/")
        resolved.append(provider)

    # Optional per-household failover order ("order": [provider names]) —
    # ranked names come first in the given order; unranked keep their
    # relative env order behind them. The primary select still floats its
    # provider to the very front.
    order = cfg.get("order")
    if isinstance(order, list) and order:
        rank = {name: i for i, name in enumerate(order)}
        resolved.sort(key=lambda p: rank.get(p.name, len(order)))
    return resolved or plan


async def first_available(plan: list) -> AIProvider | None:
    """First provider that passes availability (with a short negative cache)."""
    now = time.monotonic()
    for provider in plan:
        cached = _health.get(provider.name, now)
        ok = cached if cached is not None else await provider.available()
        _health.set(provider.name, ok, now)
        if ok:
            found: AIProvider | None = provider
            return found
    return None


async def available_providers(plan: list) -> list:
    """All providers that pass availability, in plan order — the failover
    list for streaming calls, where the first pick can still die mid-request
    (e.g. a placeholder cloud key that `available()` cannot detect)."""
    now = time.monotonic()
    resolved = []
    for provider in plan:
        cached = _health.get(provider.name, now)
        ok = cached if cached is not None else await provider.available()
        _health.set(provider.name, ok, now)
        if ok:
            resolved.append(provider)
    return resolved


def mark_unhealthy(provider_name: str) -> None:
    """Negative-cache a provider that just failed at request time, so the
    next plan resolution skips it for the cache TTL."""
    _health.set(provider_name, False, time.monotonic())


async def status() -> dict:
    plan = build_plan()
    infos = []
    for provider in plan:
        ok = await provider.available()
        infos.append(
            ProviderInfo(
                name=provider.name,
                available=ok,
                local=provider.local,
                model=provider.model,
            )
        )
    default = next((i.name for i in infos if i.available), None)
    return {
        "default_provider": default,
        "providers": [i.__dict__ for i in infos],
    }
