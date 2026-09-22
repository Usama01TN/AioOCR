"""Jinja2 + HTMX control panel with i18n and theme support."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from ocrroute import __version__
from ocrroute.catalog.registry import get_registry
from ocrroute.config import Settings
from ocrroute.db.models import Engine, Provider, Route, Run, User
from ocrroute.db.session import get_session_factory
from ocrroute.i18n import AVAILABLE_LOCALES, DEFAULT_LOCALE, get_locale, translate
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


def _resolve_locale(request: Request) -> str:
    q = request.query_params.get("lang")
    if q:
        loc = get_locale(q)
        request.session["locale"] = loc
        return loc
    session_loc = request.session.get("locale")
    if session_loc:
        return get_locale(str(session_loc))
    cookie = request.cookies.get("ocrroute_lang")
    if cookie:
        return get_locale(cookie)
    accept = request.headers.get("accept-language") or ""
    for part in accept.split(","):
        code = part.split(";")[0].strip()
        if code:
            return get_locale(code)
    return DEFAULT_LOCALE


def _resolve_theme(request: Request) -> str:
    q = request.query_params.get("theme")
    if q in ("light", "dark", "system"):
        request.session["theme"] = q
        return q
    session_theme = request.session.get("theme")
    if session_theme in ("light", "dark", "system"):
        return str(session_theme)
    cookie = request.cookies.get("ocrroute_theme")
    if cookie in ("light", "dark", "system"):
        return cookie
    return "system"


def _nav_items(locale: str, active: str) -> list[dict[str, str]]:
    items = [
        ("overview", "/panel/", "nav.overview", "▣"),
        ("engines", "/panel/engines", "nav.engines", "⚙"),
        ("providers", "/panel/providers", "nav.providers", "🔑"),
        ("routes", "/panel/routes", "nav.routes", "↗"),
        ("playground", "/panel/playground", "nav.playground", "▷"),
        ("runs", "/panel/runs", "nav.runs", "☰"),
        ("usage", "/panel/usage", "nav.usage", "◔"),
        ("keys", "/panel/keys", "nav.keys", "▤"),
        ("batch", "/panel/batch", "nav.batch", "⧉"),
        ("tools", "/panel/tools", "nav.tools", "🧰"),
        ("settings", "/panel/settings", "nav.settings", "☆"),
        ("doctor", "/panel/doctor", "nav.doctor", "✚"),
    ]
    out = []
    for key, href, label_key, icon in items:
        out.append(
            {
                "key": key,
                "href": href,
                "label": translate(label_key, locale),
                "icon": icon,
                "active": "active" if key == active else "",
            }
        )
    return out


def create_panel_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="OcrRoute Panel", docs_url=None, redoc_url=None)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(exist_ok=True)
    (STATIC_DIR / "js").mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def ctx(request: Request, **extra: Any) -> dict[str, Any]:
        locale = _resolve_locale(request)
        theme = _resolve_theme(request)
        meta = AVAILABLE_LOCALES.get(locale, AVAILABLE_LOCALES[DEFAULT_LOCALE])
        user = request.session.get("user")
        active = extra.pop("nav_active", "overview")
        page_title_key = extra.pop("title_key", None)
        title = extra.pop("title", None)
        if page_title_key:
            title = translate(page_title_key, locale)
        if not title:
            title = translate("app.name", locale)

        def t(key: str, **kwargs: Any) -> str:
            return translate(key, locale, **kwargs)

        return {
            "request": request,
            "version": __version__,
            "user": user,
            "csrf": _csrf(request),
            "title": title,
            "locale": locale,
            "dir": meta.get("dir", "ltr"),
            "theme": theme,
            "locales": AVAILABLE_LOCALES,
            "nav": _nav_items(locale, active),
            "t": t,
            "tagline": translate("app.tagline", locale),
            **extra,
        }

    def _html(request: Request, name: str, **extra: Any) -> HTMLResponse:
        response = templates.TemplateResponse(request, name, ctx(request, **extra))
        locale = _resolve_locale(request)
        theme = _resolve_theme(request)
        response.set_cookie("ocrroute_lang", locale, max_age=365 * 24 * 3600, samesite="lax")
        response.set_cookie("ocrroute_theme", theme, max_age=365 * 24 * 3600, samesite="lax")
        return response

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
        return _html(
            request,
            "overview.html",
            title_key="overview.title",
            nav_active="overview",
            stats=stats,
            recent=recent,
        )

    @app.get("/engines", response_class=HTMLResponse)
    async def engines_page(request: Request) -> HTMLResponse:
        registry = get_registry()
        registry.discover()
        engines = registry.list()
        return _html(
            request,
            "engines.html",
            title_key="engines.title",
            nav_active="engines",
            engines=engines,
        )

    @app.get("/providers", response_class=HTMLResponse)
    async def providers_page(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        async with factory() as session:
            providers = list((await session.execute(select(Provider))).scalars().all())
        return _html(
            request,
            "providers.html",
            title_key="providers.title",
            nav_active="providers",
            providers=providers,
        )

    @app.get("/routes", response_class=HTMLResponse)
    async def routes_page(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        async with factory() as session:
            routes = list((await session.execute(select(Route))).scalars().all())
        return _html(
            request,
            "routes.html",
            title_key="routes.title",
            nav_active="routes",
            routes=routes,
        )

    @app.get("/playground", response_class=HTMLResponse)
    async def playground(request: Request) -> HTMLResponse:
        engines = get_registry().list()
        return _html(
            request,
            "playground.html",
            title_key="playground.title",
            nav_active="playground",
            engines=engines,
        )

    @app.get("/runs", response_class=HTMLResponse)
    async def runs_page(request: Request) -> HTMLResponse:
        factory = get_session_factory()
        async with factory() as session:
            runs = list(
                (await session.execute(select(Run).order_by(Run.created_at.desc()).limit(100))).scalars().all()
            )
        return _html(request, "runs.html", title_key="runs.title", nav_active="runs", runs=runs)

    @app.get("/usage", response_class=HTMLResponse)
    async def usage_page(request: Request) -> HTMLResponse:
        return _html(request, "usage.html", title_key="usage.title", nav_active="usage")

    @app.get("/keys", response_class=HTMLResponse)
    async def keys_page(request: Request) -> HTMLResponse:
        return _html(request, "keys.html", title_key="keys.title", nav_active="keys")

    @app.get("/batch", response_class=HTMLResponse)
    async def batch_page(request: Request) -> HTMLResponse:
        return _html(request, "batch.html", title_key="batch.title", nav_active="batch")

    @app.get("/tools", response_class=HTMLResponse)
    async def tools_page(request: Request) -> HTMLResponse:
        tools = get_tool_registry().list()
        return _html(
            request,
            "tools.html",
            title_key="tools.title",
            nav_active="tools",
            tools=tools,
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        return _html(
            request,
            "settings.html",
            title_key="settings.title",
            nav_active="settings",
            settings=settings,
        )

    @app.get("/doctor", response_class=HTMLResponse)
    async def doctor_page(request: Request) -> HTMLResponse:
        engines = get_registry().list()
        available = sum(1 for e in engines if e.available)
        return _html(
            request,
            "doctor.html",
            title_key="doctor.title",
            nav_active="doctor",
            engines=engines,
            available=available,
            settings=settings,
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        err = request.query_params.get("error")
        return _html(request, "login.html", title_key="login.title", nav_active="login", login_error=bool(err))

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ) -> RedirectResponse:
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
        # Keep locale/theme preferences
        locale = request.session.get("locale")
        theme = request.session.get("theme")
        request.session.clear()
        if locale:
            request.session["locale"] = locale
        if theme:
            request.session["theme"] = theme
        return RedirectResponse("/panel/login", status_code=303)

    @app.get("/prefs")
    async def set_prefs(request: Request) -> RedirectResponse:
        """Set lang/theme via query and redirect back."""
        locale = request.query_params.get("lang")
        theme = request.query_params.get("theme")
        nxt = request.query_params.get("next") or "/panel/"
        if locale:
            request.session["locale"] = get_locale(locale)
        if theme in ("light", "dark", "system"):
            request.session["theme"] = theme
        # Avoid open redirect
        if not nxt.startswith("/panel"):
            nxt = "/panel/"
        resp = RedirectResponse(nxt, status_code=303)
        if locale:
            resp.set_cookie("ocrroute_lang", get_locale(locale), max_age=365 * 24 * 3600, samesite="lax")
        if theme in ("light", "dark", "system"):
            resp.set_cookie("ocrroute_theme", theme, max_age=365 * 24 * 3600, samesite="lax")
        return resp

    @app.get("/stream")
    async def sse_stream(request: Request) -> Any:
        import asyncio
        import json

        from starlette.responses import StreamingResponse

        async def gen():
            while True:
                if await request.is_disconnected():
                    break
                payload = json.dumps({"type": "ping", "version": __version__})
                yield f"data: {payload}\n\n"
                await asyncio.sleep(5)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app
