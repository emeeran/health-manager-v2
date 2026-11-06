"""Viewer-role write gate.

Household viewers are read-only: mutating requests whose access token
resolves to a viewer membership are rejected. Read-only POST prefixes are
allowlisted — auth flows, self-scoped notifications, and the (future)
smart-search/smart-entry/chat endpoints that only read on the caller's
behalf.

Runs as middleware so coverage is total by construction; the DB check only
fires for authenticated mutations, and only blocks when the role is
*positively* determined to be viewer.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ALLOWED_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/notifications",
    "/api/v1/smart-search",
    "/api/v1/smart-entry",
    "/api/v1/conversations",
)


async def _is_viewer(request: Request) -> bool:
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.core.deps import _resolve_token
    from app.core.security import decode_access_token
    from app.models import HouseholdMember, HouseholdRole

    token = _resolve_token(request)
    if not token:
        return False
    claims = decode_access_token(token)
    if not claims or claims.get("type") != "access":
        return False
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        return False
    async with SessionLocal() as session:
        role = await session.scalar(
            select(HouseholdMember.role).where(HouseholdMember.user_id == user_id)
        )
    return role == HouseholdRole.VIEWER.value


class ViewerWriteGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if (
            request.method in MUTATING_METHODS
            and path.startswith("/api/v1")
            and not path.startswith(ALLOWED_PREFIXES)
            and await _is_viewer(request)
        ):
            return JSONResponse({"detail": "Viewer role is read-only"}, status_code=403)
        return await call_next(request)
