"""Household settings: rename + per-household AI provider config."""

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_household_membership, require_household_admin
from app.models import Household, User
from app.schemas.household import AiConfig, HouseholdInfo, HouseholdUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/household", tags=["household"])

DEFAULT_AI_CONFIG = {"primary_provider": "auto", "providers": []}


def _parse_config(household: Household) -> dict:
    if not household.settings_json:
        return dict(DEFAULT_AI_CONFIG)
    try:
        parsed = json.loads(household.settings_json)
    except ValueError:
        return dict(DEFAULT_AI_CONFIG)
    if not isinstance(parsed, dict):
        return dict(DEFAULT_AI_CONFIG)
    return parsed


@router.get("", response_model=HouseholdInfo)
async def get_household(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HouseholdInfo:
    household, role = await get_household_membership(user, db)
    return HouseholdInfo(id=household.id, name=household.name, my_role=role)


@router.patch("", response_model=HouseholdInfo)
async def rename_household(
    body: HouseholdUpdate,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> HouseholdInfo:
    household, role = result
    old = household.name
    household.name = body.name
    record_audit(
        db,
        action="household.rename",
        household_id=household.id,
        detail=f"{old!r} -> {body.name!r}",
        ip=request.client.host if request.client else None,
    )
    await db.flush()
    return HouseholdInfo(id=household.id, name=household.name, my_role=role)


@router.get("/ai-config", response_model=AiConfig)
async def get_ai_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AiConfig:
    household, _ = await get_household_membership(user, db)
    return AiConfig.model_validate({**DEFAULT_AI_CONFIG, **_parse_config(household)})


@router.put("/ai-config", response_model=AiConfig)
async def put_ai_config(
    body: AiConfig,
    request: Request,
    result: tuple = Depends(require_household_admin),
    db: AsyncSession = Depends(get_db),
) -> AiConfig:
    from fastapi import HTTPException, status

    from app.services.provider_keys import validate_base_url

    for provider in body.providers:
        if provider.base_url:
            # Reuse the credential resolver's SSRF blocklist.
            try:
                validate_base_url(provider.base_url)
            except ValueError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    household, _ = result
    household.settings_json = body.model_dump_json()
    record_audit(
        db,
        action="household.ai_config",
        household_id=household.id,
        detail=f"primary={body.primary_provider}",
        ip=request.client.host if request.client else None,
    )
    await db.flush()
    return body
