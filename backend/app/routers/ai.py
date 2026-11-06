"""AI status endpoint."""

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models import User
from app.services.ai import router as ai_router

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
async def ai_status(_: User = Depends(get_current_user)) -> dict:
    return await ai_router.status()
