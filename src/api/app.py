"""FastAPI application factory."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..shared.api import exception_registry
from ..shared.api.exception_handlers import register_all_exception_handlers
from ..shared.infrastructure.database import (
    close_db,
    ensure_indexes,
    get_db_context,
)
from ..shared.infrastructure.logging import get_logger, setup_logging
from ..shared.infrastructure.middleware import (
    AuditContextMiddleware,
    ResponseWrapperMiddleware,
)
from ..shared.infrastructure.tasks.dispatcher import task_dispatcher
from ..shared.infrastructure.tasks.scheduler import shutdown_scheduler, start_scheduler
from ..shared.utils.config import settings
from .v1.router import api_router

setup_logging()
logger = get_logger(__name__)

API_DESCRIPTION = """
Backend for NextHire AI — collected job postings, search, saved jobs,
application tracking, preferences and Gemini-scored recommendations.

## Families of endpoints

- `/api/v1/auth/*` — register and sign in (public, rate limited); me, logout.
- `/api/v1/app/*` — any signed-in user, acting on their own data.
- `/api/v1/admin/*` — admins: job sources, collection runs, moderation, users.
- `/api/v1/public/*` — anonymous counts for the landing page.

Every successful JSON response is wrapped as `{status, success: true, data}`;
every error as `{status, success: false, error, details}`.

## Authorizing requests in this page

1. Call `POST /api/v1/auth/login` (or `/register`) with an email and password.
2. Copy `access_token` from the response.
3. Click **Authorize** and paste it **without** the `Bearer ` prefix.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: create indexes, bootstrap the first admin, start the scheduler.

    Shutdown: stop the scheduler and the task pool, close the DB pool.
    """
    logger.info(f"Starting {settings.app_name}...")

    # MongoDB has no schema to migrate; each entity declares its indexes and
    # they are created here if missing (idempotent). A database that cannot
    # be reached fails startup, because serving without one is worse than
    # not starting.
    try:
        ensure_indexes()
    except Exception as e:
        logger.error(f"MongoDB index setup failed: {e}")
        raise

    if settings.setup_admin:
        try:
            from scripts.setup_admin_service import SetupAdminService

            with get_db_context() as db:
                await SetupAdminService(db).setup_admin()
        except Exception as e:
            # Never block startup on this: a broken bootstrap should not take
            # the API down, and the operator can always create the account.
            logger.error(f"Initial admin setup failed: {e}", exc_info=True)

    # Scheduled collection. Imported here rather than at the top so the
    # factory's import graph does not pull the scheduler's job in; tests build
    # the app with SCHEDULER_ENABLED=false and never start it.
    from ..modules.collection.application.use_cases.run_use_cases import (
        run_due_collections,
    )

    from ..modules.lead_finder.application.use_cases.search_use_cases import (
        SearchMaintenanceUseCase,
    )

    async def tick() -> None:
        await run_due_collections()
        # Lead Finder housekeeping: wipe Google content past its retention
        # window, and fail searches a restart left "running". Both are one
        # indexed UPDATE, so running them every tick costs nothing.
        try:
            with get_db_context() as session:
                await SearchMaintenanceUseCase(session).execute()
        except Exception as e:
            logger.error(f"Lead Finder maintenance failed: {e}", exc_info=True)

    start_scheduler(tick)

    logger.info("Application startup completed")
    yield

    logger.info("Shutting down application...")
    shutdown_scheduler()
    task_dispatcher.shutdown()
    try:
        close_db()
    except Exception as e:
        logger.error(f"Application shutdown error: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description=API_DESCRIPTION,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Same order as hgs-backend: CORS -> ResponseWrapper -> AuditContext.
    # Starlette wraps the LAST-added outermost, so a request passes through
    # AuditContext first and CORS last.
    #
    # A crash-500 never passes back through CORSMiddleware at any ordering
    # (Starlette binds the bare Exception handler outside every user
    # middleware), so `unhandled_exception_handler` adds its own CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ResponseWrapperMiddleware)
    app.add_middleware(AuditContextMiddleware)

    app.include_router(api_router)

    register_all_exception_handlers()
    exception_registry.apply_to_app(app)

    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check — outside `/api/` so it is not wrapped in the envelope."""
        return {
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get("/", tags=["Root"])
    async def root():
        """Service information."""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
