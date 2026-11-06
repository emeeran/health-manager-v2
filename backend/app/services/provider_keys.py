"""Runtime credential resolver: encrypted app_secrets rows first, env fallback.

Only allowlisted settings names can be stored. Base-URL keys are validated
against an SSRF blocklist (cloud-metadata endpoints) on both write and
resolve, so a stored URL can never redirect provider traffic at metadata
services.
"""

import ipaddress
import logging
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import AppSecret

logger = logging.getLogger(__name__)

# Failover/display order for the settings board; ALLOWED_KEYS is derived.
ALLOWED_KEYS_ORDER = (
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_BASE_URL",
    "GROQ_BASE_URL",
    "OLLAMA_BASE_URL",
    "OPENAI_MODEL",
    "GROQ_MODEL",
    "OLLAMA_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_BASE_URL",
    "GEMINI_MODEL",
    "COHERE_API_KEY",
    "COHERE_BASE_URL",
    "COHERE_MODEL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "MISTRAL_API_KEY",
    "MISTRAL_BASE_URL",
    "MISTRAL_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL",
    "HUGGINGFACE_API_KEY",
    "HUGGINGFACE_BASE_URL",
    "HUGGINGFACE_MODEL",
)

ALLOWED_KEYS = frozenset(ALLOWED_KEYS_ORDER)

_BLOCKED_HOSTS = frozenset({"metadata.google.internal"})
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # cloud instance metadata
]


def validate_base_url(url: str) -> None:
    """Reject URLs aimed at cloud-metadata endpoints. Raises ValueError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Base URL must be an absolute http(s) URL")
    if parsed.hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked host: {parsed.hostname}")
    try:
        addr = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return  # hostname, not an IP
    if any(addr in network for network in _BLOCKED_NETWORKS):
        raise ValueError("Link-local metadata addresses are not allowed")


def validate_key(name: str, value: str) -> None:
    if name not in ALLOWED_KEYS:
        raise ValueError(f"Key not configurable: {name}")
    if name.endswith("_BASE_URL"):
        validate_base_url(value)


def mask(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"••••{value[-4:]}"


async def resolve_key(db: AsyncSession, name: str) -> str:
    """Stored (decrypted) value first, then the env/config fallback."""
    if name not in ALLOWED_KEYS:
        raise ValueError(f"Key not configurable: {name}")
    row = await db.get(AppSecret, name)
    if row is not None:
        value = decrypt_secret(row.value_encrypted)
        if value:
            return value
    return getattr(get_settings(), name, "")


async def apply_stored_credentials(db: AsyncSession, providers: list) -> None:
    """Overlay stored credentials onto resolved providers (stored beats env).

    Called from the plan resolver before household overrides, so precedence
    is: household override > stored app_secret > env default. Providers
    without an entry in ALLOWED_KEYS (e.g. Ollama's key) are left as built.
    """
    for provider in providers:
        prefix = provider.name.upper()
        for suffix, attr in (
            ("API_KEY", "api_key"),
            ("BASE_URL", "base_url"),
            ("MODEL", "model"),
        ):
            name = f"{prefix}_{suffix}"
            if name not in ALLOWED_KEYS:
                continue
            value = await resolve_key(db, name)
            if suffix == "BASE_URL":
                value = value.rstrip("/")
            if value:
                setattr(provider, attr, value)


async def expand_plan_with_stored(db: AsyncSession, providers: list) -> list:
    """Materialize cloud providers configured only as stored credentials.

    build_plan() creates cloud slots from env keys alone — a desktop app
    launched from a desktop session has no shell env, so a provider the
    user configured in Settings (app_secrets) never existed to be overlaid
    and the install was stuck on Ollama. Each stored API key without a
    matching plan entry gets a provider built with the settings defaults
    for base URL/model (a stored BASE_URL/MODEL refines it in the overlay
    pass), inserted before the local tail.
    """
    from app.services.ai.openai_compat import OpenAICompatibleProvider

    settings = get_settings()
    present = {p.name for p in providers}
    rows = (
        await db.scalars(
            select(AppSecret).where(
                AppSecret.key.in_([n for n in ALLOWED_KEYS if n.endswith("_API_KEY")])
            )
        )
    ).all()
    for row in rows:
        value = decrypt_secret(row.value_encrypted)
        name = row.key.removesuffix("_API_KEY").lower()
        if not value or name in present:
            continue
        provider = OpenAICompatibleProvider(
            name,
            value,
            getattr(settings, f"{name.upper()}_BASE_URL"),
            getattr(settings, f"{name.upper()}_MODEL"),
        )
        # Cloud slots go before the local (Ollama) tail, matching build_plan.
        insert_at = next(
            (i for i, p in enumerate(providers) if getattr(p, "local", False)),
            len(providers),
        )
        providers.insert(insert_at, provider)
        present.add(name)
    return providers


async def set_key(db: AsyncSession, name: str, value: str) -> None:
    validate_key(name, value)
    row = await db.get(AppSecret, name)
    encrypted = encrypt_secret(value)
    if row is None:
        row = AppSecret(key=name, value_encrypted=encrypted or "")
    else:
        row.value_encrypted = encrypted or ""
    db.add(row)


async def delete_key(db: AsyncSession, name: str) -> bool:
    if name not in ALLOWED_KEYS:
        raise ValueError(f"Key not configurable: {name}")
    row = await db.get(AppSecret, name)
    if row is None:
        return False
    await db.delete(row)
    return True


async def key_status(db: AsyncSession, name: str) -> dict:
    """Masked status for the admin UI: where the effective value comes from."""
    row = await db.get(AppSecret, name)
    stored = None
    if row is not None:
        stored = decrypt_secret(row.value_encrypted)
    env_value = getattr(get_settings(), name, "")
    effective = stored or env_value
    return {
        "name": name,
        "set": bool(effective),
        "source": "db" if stored else ("env" if env_value else "none"),
        "value": mask(effective),
    }
