"""OcrRoute CLI — Typer + Rich."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from ocrroute import __version__

app = typer.Typer(
    name="ocrroute",
    help="OcrRoute — OCR gateway CLI",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(stderr=True)

engines_app = typer.Typer(help="Engine catalogue")
provider_app = typer.Typer(help="Providers")
cred_app = typer.Typer(help="Credentials")
route_app = typer.Typer(help="Routes")
key_app = typer.Typer(help="API keys")
runs_app = typer.Typer(help="Runs")
db_app = typer.Typer(help="Database")
config_app = typer.Typer(help="Config")

app.add_typer(engines_app, name="engines")
app.add_typer(provider_app, name="provider")
app.add_typer(cred_app, name="cred")
app.add_typer(route_app, name="route")
app.add_typer(key_app, name="key")
app.add_typer(runs_app, name="runs")
app.add_typer(db_app, name="db")
app.add_typer(config_app, name="config")


def _out(data: Any, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                console.print(f"[bold]{k}[/bold]: {v}")
        else:
            console.print(data)


@app.command()
def version(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Print version."""
    import platform
    import sys as _sys

    data = {
        "version": __version__,
        "python": _sys.version.split()[0],
        "platform": platform.platform(),
    }
    _out(data, json_out)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(20256, "--port"),
    panel_port: int = typer.Option(20257, "--panel-port"),
    reload: bool = typer.Option(False, "--reload"),
    workers: int = typer.Option(1, "--workers"),
) -> None:
    """Start the API + panel server."""
    import socket

    import uvicorn

    # Probe port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host if host != "0.0.0.0" else "127.0.0.1", port))
        except OSError:
            console.print(
                f"[red]Port {port} is busy.[/red] Choose another with --port "
                f"(never use 20128). OcrRoute default is 20256."
            )
            raise typer.Exit(1)

    from ocrroute.config import get_settings

    settings = get_settings()
    settings.port = port
    settings.host = host
    settings.panel_port = panel_port
    console.print(f"[green]OcrRoute[/green] listening on http://{host}:{port}")
    console.print(f"  panel  → http://{host}:{port}/panel")
    console.print(f"  docs   → http://{host}:{port}/v1/docs")
    uvicorn.run(
        "ocrroute.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
    )


@app.command()
def setup() -> None:
    """Guided first-run: admin user, first provider, key, route."""
    import asyncio

    from argon2 import PasswordHasher
    from sqlalchemy import select

    from ocrroute.config import get_settings
    from ocrroute.crypto import SecretBox, generate_api_key, new_ulid
    from ocrroute.db.models import ApiKey, Engine, Provider, Route, RouteMember, User
    from ocrroute.db.session import get_session_factory, init_db
    from ocrroute.runtime.service import OcrService

    settings = get_settings()
    settings.ensure_dirs()

    async def _run() -> None:
        await init_db(settings)
        factory = get_session_factory(settings)
        async with factory() as session:
            svc = OcrService(settings)
            await svc.ensure_engines_synced(session)

            username = typer.prompt("Admin username", default="admin")
            password = typer.prompt("Admin password", hide_input=True, confirmation_prompt=True)
            ph = PasswordHasher()
            existing = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if existing is None:
                session.add(User(username=username, password_hash=ph.hash(password), role="admin"))
                console.print(f"[green]Created user[/green] {username}")

            # Local Tesseract provider if available
            eng = await session.get(Engine, "Tesseract")
            if eng and eng.available:
                provs = (
                    await session.execute(select(Provider).where(Provider.engine_id == "Tesseract"))
                ).scalars().all()
                if not provs:
                    p = Provider(
                        id=new_ulid(),
                        engine_id="Tesseract",
                        label="tesseract-local",
                        enabled=True,
                    )
                    session.add(p)
                    await session.flush()
                    r = Route(
                        id=new_ulid(),
                        name="default",
                        description="Default local-first route",
                        strategy="local_first",
                        is_default=True,
                        stop_condition={"min_chars": 1},
                    )
                    session.add(r)
                    await session.flush()
                    session.add(
                        RouteMember(
                            id=new_ulid(),
                            route_id=r.id,
                            provider_id=p.id,
                            order_index=0,
                        )
                    )
                    console.print("[green]Created default route[/green] with Tesseract")

            raw, key_hash, prefix = generate_api_key()
            session.add(
                ApiKey(
                    id=new_ulid(),
                    name="default",
                    key_hash=key_hash,
                    key_prefix=prefix,
                    scopes=["admin", "ocr:read", "ocr:write"],
                )
            )
            await session.commit()
            console.print("[green]API key created (save it — shown once):[/green]")
            console.print(raw)

    asyncio.run(_run())
    console.print(f"\nData dir: {settings.home}")
    console.print("Start with: [bold]ocrroute serve[/bold]")


@app.command()
def doctor(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Diagnostics."""
    import asyncio
    import platform
    import sys as _sys

    from ocrroute.catalog.registry import get_registry
    from ocrroute.config import get_settings
    from ocrroute.db.session import init_db

    settings = get_settings()

    async def _run() -> dict[str, Any]:
        await init_db(settings)
        reg = get_registry()
        reg.discover()
        return {
            "version": __version__,
            "python": _sys.version,
            "platform": platform.platform(),
            "home": str(settings.home),
            "db": str(settings.db_path),
            "engines": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "available": e.available,
                    "import_error": e.import_error,
                    "install_hint": e.install_hint,
                }
                for e in reg.list()
            ],
        }

    data = asyncio.run(_run())
    if json_out:
        typer.echo(json.dumps(data, indent=2))
    else:
        console.print(f"OcrRoute {data['version']}")
        console.print(f"Home: {data['home']}")
        table = Table("Engine", "Kind", "Available", "Hint")
        for e in data["engines"]:
            table.add_row(
                e["id"],
                e["kind"],
                "yes" if e["available"] else "no",
                (e.get("install_hint") or "")[:40],
            )
        console.print(table)


@engines_app.command("list")
def engines_list(
    kind: Optional[str] = typer.Option(None, "--kind"),
    available: bool = typer.Option(False, "--available"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    from ocrroute.catalog.registry import get_registry

    reg = get_registry()
    items = reg.list(kind=kind, available=True if available else None)
    if json_out:
        typer.echo(json.dumps([e.to_dict() for e in items], indent=2))
        return
    table = Table("ID", "Kind", "Available", "Vendor", "Cost")
    for e in items:
        table.add_row(e.id, e.kind, "yes" if e.available else "no", e.vendor, e.cost_model)
    console.print(table)


@engines_app.command("refresh")
def engines_refresh() -> None:
    from ocrroute.catalog.registry import get_registry

    get_registry().discover(force=True)
    console.print(f"Discovered {len(get_registry().engines)} engines")


@engines_app.command("options")
def engines_options(engine: str = typer.Argument(...), json_out: bool = typer.Option(False, "--json")) -> None:
    from ocrroute.catalog.registry import get_registry

    info = get_registry().get(engine)
    if not info:
        console.print(f"[red]Unknown engine[/red] {engine}")
        raise typer.Exit(1)
    _out(info.option_schema, json_out or True)


@app.command()
def ocr(
    source: str = typer.Argument(..., help="File path or URL"),
    route: Optional[str] = typer.Option(None, "--route"),
    engine: Optional[str] = typer.Option(None, "--engine"),
    lang: Optional[str] = typer.Option(None, "--lang"),
    pages: Optional[str] = typer.Option(None, "--pages"),
    out: str = typer.Option("text", "--out"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run OCR on a file or URL (zero-config friendly)."""
    import asyncio

    from ocrroute.config import get_settings
    from ocrroute.db.session import get_session_factory, init_db
    from ocrroute.runtime.service import OcrService

    settings = get_settings()

    async def _run() -> dict[str, Any]:
        await init_db(settings)
        factory = get_session_factory(settings)
        async with factory() as session:
            svc = OcrService(settings)
            await svc.ensure_engines_synced(session)
            kwargs: dict[str, Any] = {
                "route": route,
                "engine": engine,
                "language": lang,
                "pages": pages,
                "output": [out] if out != "json" else ["json", "text"],
                "cache": True,
            }
            if source.startswith("http://") or source.startswith("https://"):
                kwargs["url"] = source
            else:
                kwargs["path"] = source
            env = await svc.run_ocr(session, **kwargs)
            await session.commit()
            return env

    env = asyncio.run(_run())
    if json_out or out == "json":
        typer.echo(json.dumps(env, indent=2, default=str))
    else:
        text = (env.get("result") or {}).get("ParsedText") or ""
        typer.echo(text)
        routing = env.get("routing") or {}
        console.print(
            f"[dim]engine={routing.get('winning_engine')} strategy={routing.get('strategy')} "
            f"attempts={routing.get('attempt_count')}[/dim]"
        )
    if output_dir and env.get("artifacts"):
        output_dir.mkdir(parents=True, exist_ok=True)


@app.command()
def batch(
    path: str = typer.Argument(...),
    route: Optional[str] = None,
    concurrency: int = 4,
    recursive: bool = False,
    out: str = "text",
) -> None:
    """Batch OCR a directory or glob."""
    import asyncio
    from glob import glob as _glob

    paths = []
    p = Path(path)
    if p.is_dir():
        pattern = "**/*" if recursive else "*"
        for f in p.glob(pattern):
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".pdf", ".webp"}:
                paths.append(str(f))
    else:
        paths = _glob(path)
    console.print(f"Batch: {len(paths)} files")

    async def _run() -> None:
        from ocrroute.config import get_settings
        from ocrroute.db.session import get_session_factory, init_db
        from ocrroute.runtime.service import OcrService

        settings = get_settings()
        await init_db(settings)
        factory = get_session_factory(settings)
        svc = OcrService(settings)
        async with factory() as session:
            for f in paths:
                try:
                    env = await svc.run_ocr(session, path=f, route=route, output=[out])
                    console.print(f"[green]ok[/green] {f} chars={env.get('usage',{}).get('chars')}")
                except Exception as exc:
                    console.print(f"[red]fail[/red] {f}: {exc}")
            await session.commit()

    asyncio.run(_run())


@key_app.command("create")
def key_create(
    name: str = typer.Option(..., "--name"),
    scope: list[str] = typer.Option(["ocr:write", "ocr:read"], "--scope"),
) -> None:
    import asyncio

    from ocrroute.config import get_settings
    from ocrroute.crypto import generate_api_key, new_ulid
    from ocrroute.db.models import ApiKey
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> str:
        settings = get_settings()
        await init_db(settings)
        factory = get_session_factory(settings)
        raw, key_hash, prefix = generate_api_key()
        async with factory() as session:
            session.add(
                ApiKey(
                    id=new_ulid(),
                    name=name,
                    key_hash=key_hash,
                    key_prefix=prefix,
                    scopes=list(scope),
                )
            )
            await session.commit()
        return raw

    raw = asyncio.run(_run())
    console.print("[green]Key (shown once):[/green]")
    typer.echo(raw)


@key_app.command("list")
def key_list(json_out: bool = typer.Option(False, "--json")) -> None:
    import asyncio

    from sqlalchemy import select

    from ocrroute.config import get_settings
    from ocrroute.db.models import ApiKey
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> list[dict[str, Any]]:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(ApiKey))).scalars().all()
            return [
                {"id": k.id, "name": k.name, "prefix": k.key_prefix, "enabled": k.enabled, "scopes": k.scopes}
                for k in rows
            ]

    data = asyncio.run(_run())
    _out(data if json_out else data, json_out)
    if not json_out:
        table = Table("ID", "Name", "Prefix", "Enabled")
        for k in data:
            table.add_row(k["id"][:10], k["name"], k["prefix"], str(k["enabled"]))
        console.print(table)


@key_app.command("revoke")
def key_revoke(key_id: str = typer.Argument(...)) -> None:
    import asyncio

    from ocrroute.config import get_settings
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> None:
        from ocrroute.db.models import ApiKey

        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            k = await session.get(ApiKey, key_id)
            if k:
                k.enabled = False
                await session.commit()
                console.print("revoked")
            else:
                console.print("[red]not found[/red]")
                raise typer.Exit(1)

    asyncio.run(_run())


@db_app.command("migrate")
def db_migrate() -> None:
    import asyncio

    from ocrroute.config import get_settings
    from ocrroute.db.session import init_db

    asyncio.run(init_db(get_settings()))
    console.print("schema ready")


@db_app.command("backup")
def db_backup(dest: Path = typer.Argument(...)) -> None:
    import sqlite3

    from ocrroute.config import get_settings

    settings = get_settings()
    src = settings.db_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(src)) as conn:
        with sqlite3.connect(str(dest)) as out:
            conn.backup(out)
    console.print(f"backed up to {dest}")


@db_app.command("restore")
def db_restore(src: Path = typer.Argument(...)) -> None:
    import shutil

    from ocrroute.config import get_settings

    settings = get_settings()
    shutil.copy2(src, settings.db_path)
    console.print(f"restored from {src}")


@db_app.command("vacuum")
def db_vacuum() -> None:
    import asyncio

    from ocrroute.config import get_settings
    from ocrroute.db.maintenance import optimize_db
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> None:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            await optimize_db(session, vacuum=True)

    asyncio.run(_run())
    console.print("vacuum done")


@db_app.command("integrity")
def db_integrity() -> None:
    import asyncio

    from sqlalchemy import text

    from ocrroute.config import get_settings
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> str:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            r = await session.execute(text("PRAGMA integrity_check"))
            return str(r.scalar())

    console.print(asyncio.run(_run()))


@config_app.command("get")
def config_get(key: Optional[str] = typer.Argument(None), json_out: bool = typer.Option(False, "--json")) -> None:
    from ocrroute.config import get_settings

    s = get_settings().model_dump_public()
    for k, v in list(s.items()):
        if hasattr(v, "as_posix"):
            s[k] = str(v)
    if key:
        _out({key: s.get(key)}, True)
    else:
        _out(s, True)


@config_app.command("export")
def config_export() -> None:
    config_get(None, True)


@runs_app.command("list")
def runs_list(limit: int = 20, json_out: bool = typer.Option(False, "--json")) -> None:
    import asyncio

    from sqlalchemy import select

    from ocrroute.config import get_settings
    from ocrroute.db.models import Run
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> list[dict[str, Any]]:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.execute(select(Run).order_by(Run.created_at.desc()).limit(limit))
            ).scalars().all()
            return [
                {"id": r.id, "status": r.status, "engine": r.requested_engine, "chars": r.chars, "ms": r.duration_ms}
                for r in rows
            ]

    data = asyncio.run(_run())
    if json_out:
        typer.echo(json.dumps(data, indent=2))
    else:
        table = Table("ID", "Status", "Engine", "Chars", "ms")
        for r in data:
            table.add_row(r["id"][:12], r["status"], str(r["engine"]), str(r["chars"]), str(r["ms"]))
        console.print(table)


@app.command()
def usage(
    group_by: str = typer.Option("day", "--group-by"),
    since: str = typer.Option("7d", "--since"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    import asyncio

    from sqlalchemy import select

    from ocrroute.config import get_settings
    from ocrroute.db.models import UsageDaily
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> list[dict[str, Any]]:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(UsageDaily).limit(100))).scalars().all()
            return [
                {"day": r.day, "engine": r.engine_id, "runs": r.runs, "cost": r.cost_cents}
                for r in rows
            ]

    data = asyncio.run(_run())
    _out(data, True if json_out else True)


@app.command()
def desktop() -> None:
    """Launch the PyQt5 desktop application."""
    try:
        from ocrroute.desktop.app import main as desktop_main
    except ImportError as exc:
        console.print(f"[red]Desktop requires PyQt5[/red]: pip install ocrroute[desktop] ({exc})")
        raise typer.Exit(1)
    desktop_main()


# provider / route stubs that talk to DB
@provider_app.command("list")
def provider_list(json_out: bool = typer.Option(False, "--json")) -> None:
    import asyncio

    from sqlalchemy import select

    from ocrroute.config import get_settings
    from ocrroute.db.models import Provider
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> list[dict[str, Any]]:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(Provider))).scalars().all()
            return [{"id": p.id, "label": p.label, "engine": p.engine_id, "enabled": p.enabled} for p in rows]

    data = asyncio.run(_run())
    if json_out:
        typer.echo(json.dumps(data, indent=2))
    else:
        table = Table("ID", "Label", "Engine", "Enabled")
        for p in data:
            table.add_row(p["id"][:10], p["label"], p["engine"], str(p["enabled"]))
        console.print(table)


@route_app.command("list")
def route_list(json_out: bool = typer.Option(False, "--json")) -> None:
    import asyncio

    from sqlalchemy import select

    from ocrroute.config import get_settings
    from ocrroute.db.models import Route
    from ocrroute.db.session import get_session_factory, init_db

    async def _run() -> list[dict[str, Any]]:
        await init_db(get_settings())
        factory = get_session_factory()
        async with factory() as session:
            rows = (await session.execute(select(Route))).scalars().all()
            return [
                {"id": r.id, "name": r.name, "strategy": r.strategy, "default": r.is_default}
                for r in rows
            ]

    data = asyncio.run(_run())
    if json_out:
        typer.echo(json.dumps(data, indent=2))
    else:
        table = Table("Name", "Strategy", "Default")
        for r in data:
            table.add_row(r["name"], r["strategy"], "yes" if r["default"] else "")
        console.print(table)


if __name__ == "__main__":
    app()
