"""Nightly maintenance: cache expiry, retention rollup, vacuum."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.db.models import Attempt, CacheEntry, Run, UsageDaily
from ocrroute.logutil import get_logger

log = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def expire_cache(session: AsyncSession) -> int:
    now = _utcnow().replace(microsecond=0).isoformat()
    result = await session.execute(delete(CacheEntry).where(CacheEntry.expires_at < now))
    count = result.rowcount or 0
    log.info("cache_expired", count=count)
    return count


async def rollup_and_prune(session: AsyncSession, retention_days: int = 30) -> dict[str, int]:
    """Aggregate old runs into usage_daily then delete them."""
    cutoff_dt = _utcnow() - timedelta(days=retention_days)
    cutoff = cutoff_dt.replace(microsecond=0).isoformat()

    rows = (
        (
            await session.execute(
                select(Run).where(
                    Run.created_at < cutoff, Run.status.in_(("succeeded", "failed", "cached"))
                )
            )
        )
        .scalars()
        .all()
    )

    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    run_ids: list[str] = []
    for run in rows:
        day = (run.created_at or "")[:10]
        key = (day, run.requested_engine or "", "", run.api_key_id or "")
        bucket = buckets.setdefault(
            key,
            {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "pages": 0,
                "chars": 0,
                "cost_cents": 0.0,
                "latencies": [],
            },
        )
        bucket["runs"] += 1
        if run.status in ("succeeded", "cached"):
            bucket["successes"] += 1
        else:
            bucket["failures"] += 1
        bucket["pages"] += run.page_count or 0
        bucket["chars"] += run.chars or 0
        bucket["cost_cents"] += run.cost_cents or 0.0
        if run.duration_ms:
            bucket["latencies"].append(run.duration_ms)
        run_ids.append(run.id)

    for (day, engine_id, provider_id, api_key_id), b in buckets.items():
        lats = sorted(b["latencies"])
        p50 = p95 = None
        if lats:
            p50 = float(lats[len(lats) // 2])
            p95 = float(lats[min(len(lats) - 1, int(len(lats) * 0.95))])
        existing = (
            await session.execute(
                select(UsageDaily).where(
                    UsageDaily.day == day,
                    UsageDaily.engine_id == engine_id,
                    UsageDaily.provider_id == provider_id,
                    UsageDaily.api_key_id == api_key_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.runs += b["runs"]
            existing.successes += b["successes"]
            existing.failures += b["failures"]
            existing.pages += b["pages"]
            existing.chars += b["chars"]
            existing.cost_cents += b["cost_cents"]
            if p50 is not None:
                existing.p50_ms = p50
            if p95 is not None:
                existing.p95_ms = p95
        else:
            session.add(
                UsageDaily(
                    day=day,
                    engine_id=engine_id,
                    provider_id=provider_id,
                    api_key_id=api_key_id,
                    runs=b["runs"],
                    successes=b["successes"],
                    failures=b["failures"],
                    pages=b["pages"],
                    chars=b["chars"],
                    cost_cents=b["cost_cents"],
                    p50_ms=p50,
                    p95_ms=p95,
                )
            )

    if run_ids:
        await session.execute(delete(Attempt).where(Attempt.run_id.in_(run_ids)))
        await session.execute(delete(Run).where(Run.id.in_(run_ids)))

    await session.commit()
    log.info("rollup_prune", runs=len(run_ids), buckets=len(buckets))
    return {"runs_pruned": len(run_ids), "buckets": len(buckets)}


async def optimize_db(session: AsyncSession, vacuum: bool = False) -> None:
    await session.execute(text("PRAGMA optimize"))
    if vacuum:
        await session.execute(text("VACUUM"))
    await session.commit()


async def reconcile_interrupted(session: AsyncSession) -> int:
    """Mark runs left in running/queued state after a crash as failed."""
    rows = (
        (await session.execute(select(Run).where(Run.status.in_(("running", "queued")))))
        .scalars()
        .all()
    )
    now = _utcnow().replace(microsecond=0).isoformat()
    for run in rows:
        run.status = "failed"
        run.error_code = "interrupted"
        run.error_message = "Server restarted while run was in progress"
        run.finished_at = now
    await session.commit()
    if rows:
        log.info("reconciled_interrupted", count=len(rows))
    return len(rows)
