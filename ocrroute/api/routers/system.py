"""Health, ready, version, doctor, metrics."""

from __future__ import annotations

import platform
import sys
from typing import Any

from fastapi import APIRouter, Depends
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from ocrroute import __version__
from ocrroute.api.deps import db_session, settings_dep
from ocrroute.catalog.registry import get_registry
from ocrroute.config import Settings
from ocrroute.db.models import Engine, Provider
from ocrroute.runtime.queue import get_gate

router = APIRouter(tags=["system"])

OCR_REQUESTS = Counter("ocrroute_ocr_requests_total", "OCR requests", ["status"])
OCR_LATENCY = Histogram("ocrroute_ocr_duration_seconds", "OCR latency")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    await session.execute(text("SELECT 1"))
    providers = (
        await session.execute(select(Provider).where(Provider.enabled.is_(True)).limit(1))
    ).scalar_one_or_none()
    engines = (
        await session.execute(select(Engine).where(Engine.available == 1).limit(1))
    ).scalar_one_or_none()
    ok = providers is not None or engines is not None
    return {
        "status": "ready" if ok else "degraded",
        "database": True,
        "has_provider_or_engine": ok,
    }


@router.get("/version")
async def version() -> dict[str, str]:
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


@router.get("/doctor")
async def doctor(
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    registry = get_registry()
    registry.discover()
    engines = [
        {
            "id": e.id,
            "kind": e.kind,
            "available": e.available,
            "import_error": e.import_error,
            "install_hint": e.install_hint,
        }
        for e in registry.list()
    ]
    # Tesseract binary probe
    tesseract_cmd = None
    try:
        from pathlib import Path
        from shutil import which

        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
            which("tesseract"),
        ]
        for c in candidates:
            if c and Path(c).exists():
                tesseract_cmd = c
                break
    except Exception:
        pass

    db_ok = True
    try:
        await session.execute(text("PRAGMA integrity_check"))
    except Exception:
        db_ok = False

    gate = get_gate()
    return {
        "version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "home": str(settings.home),
        "database": {"path": str(settings.db_path), "ok": db_ok},
        "tesseract": tesseract_cmd,
        "engines": engines,
        "queue_waiting": gate.waiting,
        "port": settings.port,
    }


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
