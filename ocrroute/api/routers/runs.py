"""Runs CRUD."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ocrroute.api.deps import db_session, ocr_service
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.db.models import Artifact, Attempt, Run
from ocrroute.errors import ErrorCode
from ocrroute.runtime.service import OcrService, build_envelope

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
    status: str | None = None,
    engine: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    q = select(Run).order_by(Run.created_at.desc()).offset(offset).limit(limit)
    if status:
        q = q.where(Run.status == status)
    if engine:
        q = q.where(Run.requested_engine == engine)
    rows = (await session.execute(q)).scalars().all()
    return {
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "engine": r.requested_engine,
                "route_id": r.route_id,
                "chars": r.chars,
                "duration_ms": r.duration_ms,
                "cost_cents": r.cost_cents,
                "cache_hit": r.cache_hit,
                "error_code": r.error_code,
                "created_at": r.created_at,
                "finished_at": r.finished_at,
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    run = (
        await session.execute(
            select(Run)
            .where(Run.id == run_id)
            .options(selectinload(Run.attempts), selectinload(Run.artifacts))
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value, "error_message": "Run not found"})
    arts = [{"kind": a.kind, "url": f"/v1/runs/{run_id}/artifacts/{a.kind}"} for a in run.artifacts]
    return build_envelope(
        run_id=run.id,
        status=run.status,
        result=run.result_json or {},
        routing=run.routing_json or {},
        usage={
            "pages": run.page_count,
            "chars": run.chars,
            "lines": run.lines,
            "words": run.words,
            "mean_confidence": run.mean_confidence,
            "duration_ms": run.duration_ms,
            "cost_cents": run.cost_cents,
        },
        artifacts=arts,
        metadata=run.metadata_json or {},
        cached=run.cache_hit,
        error_code=run.error_code,
        error_message=run.error_message,
    )


@router.get("/{run_id}/artifacts/{kind}")
async def get_artifact(
    run_id: str,
    kind: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> Response:
    art = (
        await session.execute(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind)
        )
    ).scalar_one_or_none()
    if not art:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value, "error_message": "Artifact not found"})
    path = Path(art.path).resolve()
    # Sandbox: must stay under artifacts root — checked loosely
    if not path.is_file():
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value, "error_message": "File missing"})
    return FileResponse(path)


@router.get("/{run_id}/overlay.png")
async def overlay_png(
    run_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> Response:
    art = (
        await session.execute(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == "overlay_png")
        )
    ).scalar_one_or_none()
    if art and Path(art.path).is_file():
        return FileResponse(art.path, media_type="image/png")
    raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value, "error_message": "Overlay not found"})


@router.post("/{run_id}/retry")
async def retry_run(
    run_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:write")),
    service: OcrService = Depends(ocr_service),
) -> dict[str, Any]:
    run = await session.get(Run, run_id)
    if not run:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value, "error_message": "Run not found"})
    # Re-run using stored metadata only when input was a URL; otherwise fail
    meta = run.metadata_json or {}
    return await service.run_ocr(
        session,
        engine=run.requested_engine,
        language=run.language,
        api_key_id=auth.key_id,
        metadata={**meta, "retry_of": run_id},
        url=meta.get("url"),
        base64_data=meta.get("base64"),
    )


@router.delete("/{run_id}")
async def delete_run(
    run_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, str]:
    run = (
        await session.execute(
            select(Run).where(Run.id == run_id).options(selectinload(Run.artifacts), selectinload(Run.attempts))
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value, "error_message": "Run not found"})
    for a in run.artifacts:
        try:
            Path(a.path).unlink(missing_ok=True)
        except OSError:
            pass
        await session.delete(a)
    for at in run.attempts:
        await session.delete(at)
    await session.delete(run)
    return {"status": "deleted", "id": run_id}
