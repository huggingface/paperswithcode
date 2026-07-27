"""
FastAPI backend for PapersWithCode API.

This module provides a FastAPI application that re-implements the deprecated
PapersWithCode API, starting with the Paper endpoints. It integrates with the
PostgreSQL database and provides compatible API responses.
"""

import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.services.runtime_validation import validate_runtime
from backend.utils.exceptions import PaperNotFoundError, DatabaseError

# Requests slower than this (in milliseconds) are logged so production slow
# pages can be correlated without ad-hoc instrumentation. Tune via the
# `PWC_SLOW_REQUEST_MS` env var.
import os

_SLOW_REQUEST_MS = float(os.getenv("PWC_SLOW_REQUEST_MS", "1000"))
_timing_logger = logging.getLogger("backend.timing")


def _is_mutable_paper_detail_path(path: str) -> bool:
    if path.startswith("/api/v1/papers/arxiv/"):
        return True

    if not path.startswith("/api/v1/papers/"):
        return False

    suffix = path.removeprefix("/api/v1/papers/")
    if suffix in {"search", "recent", "stats", "trending"}:
        return False

    return bool(suffix) and "/" not in suffix


# Read-only public API prefixes that are safe to cache briefly in the browser
# and any shared CDN. These power list/detail pages on the marketing site
# (methods, tasks, datasets, ...). Auth/session paths (`/me`, `/auth`,
# `/cron`) are deliberately excluded so signed-in state stays fresh.
# Trailing slash makes prefix matches accurate (e.g. `/api/v1/papers` would
# otherwise also match `/api/v1/papers-archive/...` if that route ever
# appeared).
_PUBLIC_CACHEABLE_PREFIXES = (
    "/api/v1/papers/",
    "/api/v1/methods/",
    "/api/v1/tasks/",
    "/api/v1/datasets/",
    "/api/v1/areas/",
    "/api/v1/metrics/",
    "/api/v1/repositories/",
    "/api/v1/project-pages/",
    "/api/v1/authors/",
    "/api/v1/conferences/",
    "/api/v1/organizations/",
)

# Endpoints that must never be cached even on GET because their response
# depends on the signed-in user / session cookie. Trailing slash on each
# prefix prevents false matches like `/api/v1/me` accidentally matching
# `/api/v1/methods/...`.
_PRIVATE_GET_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/me/",
    "/api/v1/cron/",
    "/api/v1/admin/",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    settings = get_settings()
    print("🚀 Starting PapersWithCode API server")
    print(f"📊 Database: {settings.database_log_identifier}")
    print(f"🌍 Environment: {settings.environment}")
    print(f"📦 Release: {settings.release_id}")
    validate_runtime(settings)
    if settings.chat_enabled:
        if not settings.chat_require_auth:
            raise RuntimeError("PWC_CHAT_REQUIRE_AUTH must remain enabled")
        if not settings.hf_token:
            raise RuntimeError("PWC_HF_TOKEN is required when chat is enabled")

    maintenance_task = None
    if (
        settings.is_deployed
        and settings.environment == "staging"
        and settings.chat_enabled
    ):
        from backend.services.chat_sandbox_service import SandboxSessionManager

        async def maintain_sandboxes() -> None:
            manager = SandboxSessionManager(settings)
            while True:
                await asyncio.sleep(60)
                for operation in (
                    manager.reconcile,
                    manager.reap_idle,
                    manager.enforce_warm_cap,
                    manager.expire_inactive_snapshots,
                ):
                    try:
                        await operation()
                    except Exception as error:
                        logging.getLogger(__name__).warning(
                            "chat sandbox maintenance failed operation=%s error=%s",
                            operation.__name__,
                            type(error).__name__,
                        )

        maintenance_task = asyncio.create_task(maintain_sandboxes())

    yield

    if maintenance_task:
        maintenance_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance_task

    # Shutdown
    print("🛑 Shutting down PapersWithCode API server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="PapersWithCode API",
        description="Re-implementation of the deprecated PapersWithCode API",
        version="1.0.0",
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
        lifespan=lifespan,
    )

    # Add CORS middleware. `allow_origin_regex` is used to permit the Hugging
    # Face Space mirror (e.g. `https://<owner>-<name>.hf.space`) when the
    # `PWC_EXTRA_ALLOWED_ORIGIN_REGEX` setting is configured, without having
    # to hardcode every Space subdomain.
    cors_kwargs = dict(
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    if settings.extra_allowed_origin_regex:
        cors_kwargs["allow_origin_regex"] = settings.extra_allowed_origin_regex
    app.add_middleware(CORSMiddleware, **cors_kwargs)

    @app.middleware("http")
    async def enforce_staging_write_boundary(request, call_next):
        if settings.is_deployed and request.method not in {"GET", "HEAD", "OPTIONS"}:
            catalog_prefixes = (
                "/api/v1/papers",
                "/api/v1/tasks",
                "/api/v1/methods",
                "/api/v1/datasets",
                "/api/v1/evaluations",
                "/api/v1/metrics",
                "/api/v1/conferences",
                "/api/v1/organizations",
                "/api/v1/repositories",
                "/api/v1/external-resources",
                "/api/thumbnails",
            )
            is_thumbnail_mutation = request.url.path.startswith("/api/thumbnails")
            is_staging_catalog_mutation = settings.environment == "staging" and any(
                request.url.path.startswith(prefix) for prefix in catalog_prefixes[:-1]
            )
            if is_staging_catalog_mutation or (
                is_thumbnail_mutation and not settings.thumbnail_mutations_enabled
            ):
                return JSONResponse(
                    {
                        "detail": (
                            "Staging is preview-only for catalog and thumbnail "
                            "mutations"
                        )
                    },
                    status_code=403,
                )
        return await call_next(request)

    @app.middleware("http")
    async def log_slow_requests(request, call_next):
        # Outermost middleware (added last), so the measured duration covers
        # the whole handler including cache-header logic.
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        # Expose timing for ad-hoc debugging / curl -D.
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        if duration_ms >= _SLOW_REQUEST_MS:
            _timing_logger.warning(
                "slow request: %s %s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response

    @app.middleware("http")
    async def add_public_cache_headers(request, call_next):
        response = await call_next(request)
        if request.method != "GET":
            return response

        path = request.url.path

        # Per-paper detail rows can change (admin edits, new repos linked)
        # so keep these uncached.
        if _is_mutable_paper_detail_path(path):
            response.headers["Cache-Control"] = "no-store"
            return response

        # User-specific endpoints (bookmarks, session probes, cron dashboard)
        # must always reflect the current session.
        if any(path.startswith(prefix) for prefix in _PRIVATE_GET_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
            return response

        # Public list/detail GETs benefit from a short freshness window plus
        # a longer stale-while-revalidate so repeat navigation is instant.
        if (
            response.status_code == 200
            and "cache-control" not in response.headers
            and any(path.startswith(prefix) for prefix in _PUBLIC_CACHEABLE_PREFIXES)
        ):
            response.headers["Cache-Control"] = (
                "public, max-age=60, stale-while-revalidate=300"
            )
        return response

    # Include routers
    from backend.routers import (
        papers,
        external_resources,
        authors,
        thumbnails,
        paper_pages,
        repositories,
        areas,
        tasks,
        methods,
        datasets,
        evaluations,
        metrics,
        cron,
        auth,
        bookmarks,
        preferences,
        pending_edits,
        conferences,
        organizations,
        chat,
        codex_add_evals,
        codex_enrich_paper,
        codex_curation_callbacks,
        stats,
        research_catalog,
    )

    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(bookmarks.router, prefix="/api/v1", tags=["bookmarks"])
    app.include_router(preferences.router, prefix="/api/v1", tags=["preferences"])
    app.include_router(pending_edits.router, prefix="/api/v1", tags=["pending_edits"])
    app.include_router(papers.router, prefix="/api/v1", tags=["papers"])
    app.include_router(research_catalog.router, prefix="/api/v1", tags=["research"])
    # External-resource ingestion endpoints share the `/papers` prefix because
    # the resulting rows live in the same `papers` table.
    app.include_router(
        external_resources.router, prefix="/api/v1", tags=["external_resources"]
    )
    app.include_router(authors.router, prefix="/api/v1", tags=["authors"])
    app.include_router(repositories.router, prefix="/api/v1", tags=["repositories"])
    app.include_router(areas.router, prefix="/api/v1", tags=["areas"])
    app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
    app.include_router(methods.router, prefix="/api/v1", tags=["methods"])
    app.include_router(datasets.router, prefix="/api/v1", tags=["datasets"])
    app.include_router(evaluations.router, prefix="/api/v1", tags=["evaluations"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    app.include_router(conferences.router, prefix="/api/v1", tags=["conferences"])
    app.include_router(organizations.router, prefix="/api/v1", tags=["organizations"])
    app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
    if settings.chat_enabled:
        app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
        from backend.chat_gateway_app import app as chat_gateway_app

        app.mount("/api/internal/chat-gateway", chat_gateway_app)
    app.include_router(codex_add_evals.router, prefix="/api/v1", tags=["admin"])
    app.include_router(codex_enrich_paper.router, prefix="/api/v1", tags=["admin"])
    app.include_router(
        codex_curation_callbacks.router, prefix="/api/v1", tags=["admin"]
    )
    app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
    # Server-rendered paper-page HTML for social previews. Mounted at the
    # app root because the public URL shape is `/paper/{id}` (not under
    # `/api/v1/...`).
    app.include_router(paper_pages.router, tags=["paper_pages"])
    if settings.cron_enabled:
        app.include_router(cron.router, prefix="/api/v1", tags=["cron"])

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "paperswithcode-api",
            "release_id": settings.release_id,
        }

    @app.get("/internal/ready", include_in_schema=False)
    async def internal_ready():
        try:
            features = validate_runtime(settings)
            if settings.environment == "staging" and settings.chat_enabled:
                from backend.database.connection import db_manager
                from backend.services.chat_sandbox_service import (
                    SandboxSessionManager,
                )
                from backend.services.runtime_validation import validate_chat_schema

                with db_manager.session_local() as db:
                    validate_chat_schema(db)
                await SandboxSessionManager(settings).validate_image_reference()
        except Exception as error:
            return JSONResponse(
                {
                    "status": "not_ready",
                    "reason": str(error)[:200],
                },
                status_code=503,
            )
        route_paths = {route.path for route in app.routes}
        has_chat_routes = any(path.startswith("/api/v1/chat") for path in route_paths)
        if has_chat_routes != settings.chat_enabled:
            return JSONResponse(
                {"status": "not_ready", "reason": "chat route manifest mismatch"},
                status_code=503,
            )
        return {
            "status": "ready",
            "environment": settings.environment,
            "release_id": settings.release_id,
            "features": features,
            "frontend_assets_valid": True,
            "thumbnail_store_valid": True,
        }

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "PapersWithCode API",
            "version": "1.0.0",
            "description": "Re-implementation of the deprecated PapersWithCode API",
            "docs": "/docs" if settings.environment == "development" else None,
        }

    # Global exception handlers
    @app.exception_handler(PaperNotFoundError)
    async def paper_not_found_handler(request, exc: PaperNotFoundError):
        return JSONResponse(
            status_code=404, content={"error": "Paper not found", "detail": str(exc)}
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request, exc: DatabaseError):
        return JSONResponse(
            status_code=500, content={"error": "Database error", "detail": str(exc)}
        )

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
