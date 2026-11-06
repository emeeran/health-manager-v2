"""Instance administration: runtime provider credentials (app_secrets),
provider status, and connection tests.

Household-admin guarded — v2 instances are single-household, so the
household admin is the instance operator.
"""

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.household import ProviderKeySet
from app.services import provider_keys
from app.services.audit import record_audit

from app.core.deps import require_household_admin
from app.services.provider_keys import ALLOWED_KEYS_ORDER

router = APIRouter(prefix="/system", tags=["system"])


async def _resolved_plan(db: AsyncSession):
    """Failover plan with stored credentials applied."""
    from app.services.ai import router as ai_router
    from app.services.provider_keys import apply_stored_credentials, expand_plan_with_stored

    plan = await expand_plan_with_stored(db, ai_router.build_plan())
    await apply_stored_credentials(db, plan)
    return plan


@router.get("/ai-providers")
async def list_ai_providers(
    _: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Configured providers in failover order (env + stored credentials)."""
    plan = await _resolved_plan(db)
    return {
        "providers": [
            {
                "name": p.name,
                "model": p.model,
                "local": bool(getattr(p, "local", False)),
            }
            for p in plan
        ]
    }


@router.post("/ai-providers/{name}/test")
async def test_ai_provider(
    name: str,
    _: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ping a provider with a minimal completion; feeds the health cache so
    the router's circuit breaker reflects the result. Returns 200 with
    ok=false on failure — the UI renders the error, not an HTTP failure."""
    from app.services.ai import router as ai_router

    plan = await _resolved_plan(db)
    provider = next((p for p in plan if p.name == name), None)
    if provider is None:
        raise HTTPException(404, f"Provider not configured: {name}")

    started = time.monotonic()
    try:
        # 512 so reasoning models (which spend budget before content) still
        # produce a non-empty answer; a 5-token budget reads as a failure.
        reply = await asyncio.wait_for(
            provider.complete("Reply with the single word OK.", max_tokens=512),
            timeout=25,
        )
        latency = int((time.monotonic() - started) * 1000)
        ok = bool(reply and reply.strip())
        ai_router.health_cache.set(name, ok, time.monotonic())
        return {
            "ok": ok,
            "latency_ms": latency,
            "model": provider.model,
            "error": None if ok else "Empty reply from provider",
        }
    except Exception as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_router.health_cache.set(name, False, time.monotonic())
        return {
            "ok": False,
            "latency_ms": latency,
            "model": provider.model,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


@router.get("/ai-providers/{name}/models")
async def list_provider_models(
    name: str,
    _: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Live model catalogue for a provider (settings board's model picker).
    Honours stored credentials and household base-URL overrides."""
    plan = await _resolved_plan(db)
    provider = next((p for p in plan if p.name == name), None)
    if provider is None:
        raise HTTPException(404, f"Provider not configured: {name}")

    lister = getattr(provider, "list_models", None)
    if lister is None:
        raise HTTPException(404, f"Provider {name} does not expose a model list")
    try:
        models = sorted(await asyncio.wait_for(lister(), timeout=25))
    except Exception as exc:
        raise HTTPException(
            502, f"Could not list models for {name}: {type(exc).__name__}: {exc}"[:300]
        ) from exc
    return {"models": models}


@router.get("/provider-keys")
async def list_provider_keys(
    _: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    statuses = [await provider_keys.key_status(db, name) for name in ALLOWED_KEYS_ORDER]
    return {"keys": statuses}


@router.get("/web-factcheck")
async def web_factcheck_status(
    _: tuple = Depends(require_household_admin),
) -> dict:
    """Whether the audit agent may reach a SearXNG instance.

    Consent is still per member; this only reports the instance capability
    so Settings can show an honest status without exposing the URL.
    """
    settings = get_settings()
    return {
        "enabled": settings.WEB_FACTCHECK_ENABLED,
        "configured": bool(settings.SEARXNG_URL),
        "max_claims": settings.WEB_FACTCHECK_MAX_CLAIMS,
        "max_results": settings.WEB_FACTCHECK_MAX_RESULTS,
    }


@router.put("/provider-keys/{name}")
async def set_provider_key(
    name: str,
    body: ProviderKeySet,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = result
    value = body.value
    try:
        await provider_keys.set_key(db, name, value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record_audit(
        db,
        action="system.key_set",
        household_id=household.id,
        detail=name,
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return await provider_keys.key_status(db, name)


@router.delete("/provider-keys/{name}")
async def delete_provider_key(
    name: str,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    household, _ = result
    try:
        removed = await provider_keys.delete_key(db, name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not removed:
        raise HTTPException(404, "Key not stored")
    record_audit(
        db,
        action="system.key_deleted",
        household_id=household.id,
        detail=name,
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return await provider_keys.key_status(db, name)
