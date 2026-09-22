"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from ocrroute import __version__
from ocrroute.api.routers import (
    engines,
    jobs,
    keys,
    ocr,
    providers,
    routes,
    runs,
    settings_api,
    system,
    tools,
    usage,
)
from ocrroute.config import Settings, get_settings
from ocrroute.crypto import ensure_secret_key
from ocrroute.db.maintenance import reconcile_interrupted
from ocrroute.db.session import dispose_db, get_session_factory, init_db
from ocrroute.errors import OcrRouteError
from ocrroute.logutil import get_logger, setup_logging
from ocrroute.runtime.service import OcrService

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    setup_logging(settings.log_level, settings.log_json)
    ensure_secret_key(settings)
    await init_db(settings)
    factory = get_session_factory(settings)
    async with factory() as session:
        await reconcile_interrupted(session)
        svc = OcrService(settings)
        await svc.ensure_engines_synced(session)
        await session.commit()
    log.info("ocrroute_started", version=__version__, port=settings.port)
    yield
    await dispose_db()
    log.info("ocrroute_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="OcrRoute",
        description=(
            "OcrRoute is an OCR gateway for multi-engine text extraction: one HTTP endpoint "
            "in front of local and cloud OCR engines, with routing, load balancing, retries "
            "and fallbacks — plus quotas, caching, cost tracking and observability."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/v1/docs",
        openapi_url="/v1/openapi.json",
        redoc_url="/v1/redoc",
    )
    app.state.settings = settings

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    secret = ensure_secret_key(settings)
    app.add_middleware(SessionMiddleware, secret_key=secret, session_cookie="ocrroute_session")

    @app.exception_handler(OcrRouteError)
    async def ocrroute_error_handler(_request: Request, exc: OcrRouteError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-OcrRoute-Version"] = __version__
        return response

    app.include_router(system.router, prefix="/v1")
    app.include_router(ocr.router, prefix="/v1")
    app.include_router(runs.router, prefix="/v1")
    app.include_router(jobs.router, prefix="/v1")
    app.include_router(engines.router, prefix="/v1")
    app.include_router(providers.router, prefix="/v1")
    app.include_router(routes.router, prefix="/v1")
    app.include_router(keys.router, prefix="/v1")
    app.include_router(usage.router, prefix="/v1")
    app.include_router(settings_api.router, prefix="/v1")
    app.include_router(tools.router, prefix="/v1")

    # Mount panel
    try:
        from ocrroute.panel.app import create_panel_app

        panel = create_panel_app(settings)
        app.mount("/panel", panel)
    except Exception as exc:
        log.warning("panel_mount_failed", error=str(exc))

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "OcrRoute",
            "version": __version__,
            "docs": "/v1/docs",
            "panel": "/panel",
            "health": "/v1/health",
        }

    return app
