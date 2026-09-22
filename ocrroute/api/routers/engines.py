"""Engine catalogue endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.api.deps import db_session, ocr_service
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.catalog.registry import get_registry
from ocrroute.db.models import Engine
from ocrroute.errors import ErrorCode
from ocrroute.runtime.service import OcrService

router = APIRouter(prefix="/engines", tags=["engines"])


@router.get("")
async def list_engines(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
    kind: str | None = None,
    service: OcrService = Depends(ocr_service),
) -> dict[str, Any]:
    await service.ensure_engines_synced(session)
    q = select(Engine)
    if kind:
        q = q.where(Engine.kind == kind)
    rows = (await session.execute(q)).scalars().all()
    return {
        "engines": [
            {
                "id": e.id,
                "name": e.name,
                "kind": e.kind,
                "vendor": e.vendor,
                "available": bool(e.available),
                "import_error": e.import_error,
                "install_hint": e.install_hint,
                "requires_key": e.requires_key,
                "supports_pdf": e.supports_pdf,
                "supports_handwriting": e.supports_handwriting,
                "supports_tables": e.supports_tables,
                "supports_overlay": e.supports_overlay,
                "languages": e.languages,
                "option_schema": e.option_schema,
                "cost_model": e.cost_model,
                "unit_price": e.unit_price,
                "enabled": e.enabled,
                "quality_score": e.quality_score,
                "homepage": e.homepage,
            }
            for e in rows
        ]
    }


@router.post("/refresh")
async def refresh_engines(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
    service: OcrService = Depends(ocr_service),
) -> dict[str, Any]:
    get_registry().discover(force=True)
    await service.ensure_engines_synced(session)
    return {"status": "refreshed", "count": len(get_registry().engines)}


@router.post("/{engine_id}/enable")
async def enable_engine(
    engine_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
    enabled: bool = True,
) -> dict[str, Any]:
    e = await session.get(Engine, engine_id)
    if not e:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    e.enabled = enabled
    return {"id": e.id, "enabled": e.enabled}


@router.post("/{engine_id}/probe")
async def probe_engine(
    engine_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
    service: OcrService = Depends(ocr_service),
) -> dict[str, Any]:
    """Run a tiny synthetic image against the engine."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (200, 60), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 20), "OcrRoute", fill="black")
    buf = BytesIO()
    img.save(buf, format="PNG")
    try:
        env = await service.run_ocr(
            session,
            raw=buf.getvalue(),
            engine=engine_id,
            cache=False,
            metadata={"origin": "panel_test"},
            api_key_id=auth.key_id,
        )
        return {"ok": env.get("status") == "succeeded", "envelope": env}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
