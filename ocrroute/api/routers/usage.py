"""Usage & stats."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.api.deps import db_session
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.db.models import Run, UsageDaily

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def usage(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
    group_by: str = Query(default="day"),
) -> dict[str, Any]:
    rows = (await session.execute(select(UsageDaily).order_by(UsageDaily.day.desc()).limit(90))).scalars().all()
    return {
        "group_by": group_by,
        "rows": [
            {
                "day": r.day,
                "engine_id": r.engine_id,
                "provider_id": r.provider_id,
                "api_key_id": r.api_key_id,
                "runs": r.runs,
                "successes": r.successes,
                "failures": r.failures,
                "pages": r.pages,
                "chars": r.chars,
                "cost_cents": r.cost_cents,
                "p50_ms": r.p50_ms,
                "p95_ms": r.p95_ms,
            }
            for r in rows
        ],
    }


@router.get("/stats/summary")
async def stats_summary(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    total = (await session.execute(select(func.count()).select_from(Run))).scalar() or 0
    succeeded = (
        await session.execute(select(func.count()).select_from(Run).where(Run.status.in_(("succeeded", "cached"))))
    ).scalar() or 0
    failed = (
        await session.execute(select(func.count()).select_from(Run).where(Run.status == "failed"))
    ).scalar() or 0
    cost = (await session.execute(select(func.coalesce(func.sum(Run.cost_cents), 0.0)))).scalar() or 0.0
    chars = (await session.execute(select(func.coalesce(func.sum(Run.chars), 0)))).scalar() or 0
    return {
        "runs_total": total,
        "runs_succeeded": succeeded,
        "runs_failed": failed,
        "success_rate": (succeeded / total) if total else 0.0,
        "cost_cents_total": float(cost),
        "chars_total": int(chars),
    }
