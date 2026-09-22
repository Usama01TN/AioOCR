"""Batch jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ocrroute.api.deps import db_session
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.db.models import Job
from ocrroute.errors import ErrorCode
from ocrroute.runtime.jobs import get_job_runner

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    job = (
        await session.execute(select(Job).where(Job.id == job_id).options(selectinload(Job.items)))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "total": job.total,
        "done": job.done,
        "failed": job.failed,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "items": [
            {
                "id": it.id,
                "source": it.source,
                "status": it.status,
                "run_id": it.run_id,
                "error_message": it.error_message,
            }
            for it in job.items
        ],
    }


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:write")),
) -> dict[str, Any]:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    get_job_runner().cancel(job_id)
    job.status = "cancelled"
    return {"id": job.id, "status": job.status}
