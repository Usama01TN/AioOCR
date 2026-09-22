"""Result cache keyed by sha256(input|route/engine|options)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.db.models import CacheEntry


def make_cache_key(
    image_sha256: str,
    *,
    route_or_engine: str,
    options: dict[str, Any] | None = None,
) -> str:
    payload = {
        "img": image_sha256,
        "target": route_or_engine,
        "opts": _normalize(options or {}),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize(obj[k]) for k in sorted(obj) if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [_normalize(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


async def cache_get(session: AsyncSession, key: str) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    row = (
        await session.execute(
            select(CacheEntry).where(CacheEntry.cache_key == key, CacheEntry.expires_at >= now)
        )
    ).scalar_one_or_none()
    if not row:
        return None
    row.hits = int(row.hits or 0) + 1
    await session.flush()
    return dict(row.result_json) if isinstance(row.result_json, dict) else row.result_json


async def cache_put(
    session: AsyncSession,
    key: str,
    *,
    run_id: str,
    result: dict[str, Any],
    ttl_seconds: int = 86400,
) -> None:
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat()
    existing = (
        await session.execute(select(CacheEntry).where(CacheEntry.cache_key == key))
    ).scalar_one_or_none()
    blob = json.dumps(result, default=str)
    if existing:
        existing.run_id = run_id
        existing.result_json = result
        existing.bytes = len(blob)
        existing.expires_at = expires
        existing.created_at = now.replace(microsecond=0).isoformat()
    else:
        session.add(
            CacheEntry(
                cache_key=key,
                run_id=run_id,
                result_json=result,
                hits=0,
                bytes=len(blob),
                created_at=now.replace(microsecond=0).isoformat(),
                expires_at=expires,
            )
        )
    await session.flush()
