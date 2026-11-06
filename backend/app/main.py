"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.database import create_tables
from app.core.role_gate import ViewerWriteGateMiddleware
from app.routers import (
    adherence,
    ai,
    ai_insights,
    allergies,
    attachments,
    auth,
    backup,
    conditions,
    conversations,
    dashboard,
    database,
    extraction,
    extraction_batch,
    fhir_import,
    growth,
    health_import,
    health,
    health_alerts,
    household,
    household_users,
    immunizations,
    labs,
    medications,
    members,
    member_emergency,
    member_history,
    notifications,
    insurance,
    jan_aushadhi,
    member_drug_info,
    member_drug_interactions,
    member_preventive,
    member_resources,
    providers,
    records,
    search,
    smart_entry,
    smart_search,
    reference_ranges,
    reminders,
    reports,
    security_audit,
    symptoms,
    vaccinations,
    share_links,
    system,
    verifications,
    vitals,
    voice_memos,
    web_push,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    await create_tables()

    # Background audits die with the process — settle their PENDING rows
    # so clients polling an old verification get a verdict instead of
    # spinning forever.
    from app.services.ai.verification import settle_orphaned_verifications

    orphaned = await settle_orphaned_verifications()
    if orphaned:
        logger.info("Settled %d orphaned pending verification(s)", orphaned)

    from app.core.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    logger.info("Startup complete (env=%s)", settings.APP_ENV)
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Family Health Manager v2",
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Viewer-role write gate — before the routers, after CORS.
    app.add_middleware(ViewerWriteGateMiddleware)
    # Ops middleware parity: GZip, request-size tiers + rate limits,
    # request-id echo, security headers.
    from app.core.middleware import configure_middleware

    configure_middleware(app)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(household.router, prefix="/api/v1")
    app.include_router(household_users.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(security_audit.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(members.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(providers.assignments, prefix="/api/v1")
    app.include_router(insurance.router, prefix="/api/v1")
    app.include_router(member_emergency.router, prefix="/api/v1")
    app.include_router(member_history.router, prefix="/api/v1")
    app.include_router(records.router, prefix="/api/v1")
    app.include_router(attachments.router, prefix="/api/v1")
    app.include_router(ai.router, prefix="/api/v1")
    app.include_router(ai_insights.router, prefix="/api/v1")
    app.include_router(health_alerts.router, prefix="/api/v1")
    app.include_router(extraction.router, prefix="/api/v1")
    app.include_router(verifications.router, prefix="/api/v1")
    app.include_router(vitals.router, prefix="/api/v1")
    app.include_router(labs.router, prefix="/api/v1")
    app.include_router(conditions.router, prefix="/api/v1")
    app.include_router(allergies.router, prefix="/api/v1")
    app.include_router(allergies.conflicts_router, prefix="/api/v1")
    app.include_router(symptoms.router, prefix="/api/v1")
    app.include_router(vaccinations.router, prefix="/api/v1")
    app.include_router(immunizations.router, prefix="/api/v1")
    app.include_router(growth.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(smart_search.router, prefix="/api/v1")
    app.include_router(smart_entry.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(database.router, prefix="/api/v1")
    app.include_router(fhir_import.router, prefix="/api/v1")
    app.include_router(health_import.router, prefix="/api/v1")
    app.include_router(extraction_batch.router, prefix="/api/v1")
    app.include_router(medications.router, prefix="/api/v1")
    app.include_router(member_drug_interactions.router, prefix="/api/v1")
    app.include_router(member_drug_info.router, prefix="/api/v1")
    app.include_router(member_resources.router, prefix="/api/v1")
    app.include_router(member_preventive.router, prefix="/api/v1")
    app.include_router(jan_aushadhi.router, prefix="/api/v1")
    app.include_router(adherence.router, prefix="/api/v1")
    app.include_router(reminders.router, prefix="/api/v1")
    app.include_router(reference_ranges.router, prefix="/api/v1")
    app.include_router(share_links.router, prefix="/api/v1")
    app.include_router(share_links.public_router, prefix="/api/v1")
    app.include_router(backup.router, prefix="/api/v1")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(web_push.router, prefix="/api/v1")
    app.include_router(voice_memos.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")

    if settings.SERVE_FRONTEND:
        _mount_spa(app, Path(settings.FRONTEND_DIST))
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA same-origin (desktop sidecar / server .deb).

    Registered LAST so API/health routes win; assets come from disk with
    long caching, everything else falls through to index.html for SPA
    deep links (traversal-guarded).
    """
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index_html = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "health", "docs", "openapi.json")):
            raise HTTPException(status_code=404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(
                candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"}
            )
        if index_html.is_file():
            return FileResponse(index_html, headers={"Cache-Control": "no-cache"})
        raise HTTPException(status_code=404, detail="Frontend not built")


app = create_app()
