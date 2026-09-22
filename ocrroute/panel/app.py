"""Jinja2 + HTMX control panel."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute import __version__
from ocrroute.api.deps import db_session
from ocrroute.catalog.registry import get_registry
from ocrroute.config import Settings
from ocrroute.crypto import hash_api_key
from ocrroute.db.models import Engine, Provider, Route, Run, User
from ocrroute.db.session import get_session_factory
from ocrroute.tools.registry import get_tool_registry

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


def create_panel_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="OcrRoute Panel", docs_url=None, redoc_url=None)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(exist_ok=True)
    (STATIC_DIR / "js").mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def ctx(request: Request, **extra: Any) -> dict[str, Any]:
        user = request.session.get("user")
        return {
            "request": request,
            "version": __version__,
            "user": user,
            "csrf": _csrf(request),
            "title": extra.pop("title", "OcrRoute"),
            **extra,
        }

    @app.get("/", response_class=HTMLResponse)
    async def overview(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        stats = {"runs": 0, "succeeded": 0, "failed": 0, "engines": 0, "providers": 0}
        recent: list[Any] = []
        async with factory() as session:
            stats["runs"] = (await session.execute(select(func.count()).select_from(Run))).scalar() or 0
            stats["succeeded"] = (
                await session.execute(
                    select(func.count()).select_from(Run).where(Run.status.in_(("succeeded", "cached")))
                )
            ).scalar() or 0
            stats["failed"] = (
                await session.execute(select(func.count()).select_from(Run).where(Run.status == "failed"))
            ).scalar() or 0
            stats["engines"] = (await session.execute(select(func.count()).select_from(Engine))).scalar() or 0
            stats["providers"] = (
                await session.execute(select(func.count()).select_from(Provider))
            ).scalar() or 0
            recent = list(
                (await session.execute(select(Run).order_by(Run.created_at.desc()).limit(20))).scalars().all()
            )
        return templates.TemplateResponse(
            request,
            "overview.html",
            ctx(request, title="Overview", stats=stats, recent=recent),
        )

    @app.get("/engines", response_class=HTMLResponse)
    async def engines_page(request: Request) -> HTMLResponse:
        registry = get_registry()
        registry.discover()
        engines = registry.list()
        return templates.TemplateResponse(
            request,
            "engines.html",
            ctx(request, title="Engines", engines=engines),
        )

    @app.get("/providers", response_class=HTMLResponse)
    async def providers_page(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        async with factory() as session:
            providers = list((await session.execute(select(Provider))).scalars().all())
        return templates.TemplateResponse(
            request,
            "providers.html",
            ctx(request, title="Providers", providers=providers),
        )

    @app.get("/routes", response_class=HTMLResponse)
    async def routes_page(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        async with factory() as session:
            routes = list((await session.execute(select(Route))).scalars().all())
        return templates.TemplateResponse(
            request,
            "routes.html",
            ctx(request, title="Routes", routes=routes),
        )

    @app.get("/playground", response_class=HTMLResponse)
    async def playground(request: Request) -> HTMLResponse:
        engines = get_registry().list()
        return templates.TemplateResponse(
            request,
            "playground.html",
            ctx(request, title="Playground", engines=engines),
        )

    @app.get("/runs", response_class=HTMLResponse)
    async def runs_page(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        async with factory() as session:
            runs = list(
                (await session.execute(select(Run).order_by(Run.created_at.desc()).limit(100))).scalars().all()
            )
        return templates.TemplateResponse(
            request,
            "runs.html",
            ctx(request, title="Runs", runs=runs),
        )

    @app.get("/usage", response_class=HTMLResponse)
    async def usage_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "usage.html",
            ctx(request, title="Usage & Cost"),
        )

    @app.get("/keys", response_class=HTMLResponse)
    async def keys_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "keys.html",
            ctx(request, title="API Keys"),
        )

    @app.get("/batch", response_class=HTMLResponse)
    async def batch_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "batch.html",
            ctx(request, title="Batch"),
        )

    @app.get("/tools", response_class=HTMLResponse)
    async def tools_page(request: Request) -> HTMLResponse:
        tools = get_tool_registry().list()
        return templates.TemplateResponse(
            request,
            "tools.html",
            ctx(request, title="Tools", tools=tools),
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "settings.html",
            ctx(request, title="Settings", settings=settings),
        )

    @app.get("/doctor", response_class=HTMLResponse)
    async def doctor_page(request: Request) -> HTMLResponse:
        engines = get_registry().list()
        return templates.TemplateResponse(
            request,
            "doctor.html",
            ctx(request, title="Doctor", engines=engines, settings=settings),
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            ctx(request, title="Login"),
        )

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ) -> RedirectResponse:
        # Simple auth: if no users, accept any and create admin
        factory = get_session_factory()
        async with factory() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if user is None:
                count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
                if count == 0:
                    from argon2 import PasswordHasher

                    ph = PasswordHasher()
                    user = User(
                        username=username,
                        password_hash=ph.hash(password),
                        role="admin",
                    )
                    session.add(user)
                    await session.commit()
                else:
                    return RedirectResponse("/panel/login?error=1", status_code=303)
            else:
                from argon2 import PasswordHasher
                from argon2.exceptions import VerifyMismatchError

                ph = PasswordHasher()
                try:
                    ph.verify(user.password_hash, password)
                except VerifyMismatchError:
                    return RedirectResponse("/panel/login?error=1", status_code=303)
            request.session["user"] = {"username": user.username, "role": user.role}
        return RedirectResponse("/panel/", status_code=303)

    @app.get("/logout")
    async def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse("/panel/login", status_code=303)

    @app.get("/stream")
    async def sse_stream(request: Request) -> Any:
        from starlette.responses import StreamingResponse
        import asyncio
        import json

        async def gen():
            while True:
                if await request.is_disconnected():
                    break
                payload = json.dumps({"type": "ping", "version": __version__})
                yield f"data: {payload}\n\n"
                await asyncio.sleep(5)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app
