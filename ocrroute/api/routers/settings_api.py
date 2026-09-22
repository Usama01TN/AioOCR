"""Settings & audit."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.api.deps import db_session, settings_dep
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.config import Settings
from ocrroute.db.models import AuditLog, Setting

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def get_settings_api(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    rows = (await session.execute(select(Setting))).scalars().all()
    overrides = {r.key: r.value_json for r in rows}
    public = settings.model_dump_public()
    public["overrides"] = overrides
    # stringify paths
    for k, v in list(public.items()):
        if hasattr(v, "as_posix"):
            public[k] = str(v)
    return public


@router.put("/settings/{key}")
async def set_setting(
    key: str,
    body: dict[str, Any],
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    from datetime import datetime, timezone

    value = body.get("value")
    row = await session.get(Setting, key)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if row:
        row.value_json = value
        row.updated_at = now
    else:
        session.add(Setting(key=key, value_json=value, updated_at=now))
    session.add(
        AuditLog(
            actor=auth.key_id or "admin",
            action="settings.set",
            target_type="setting",
            target_id=key,
            detail={"value": value},
        )
    )
    return {"key": key, "value": value}


@router.get("/audit")
async def list_audit(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
    limit: int = 100,
) -> dict[str, Any]:
    rows = (
        await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    ).scalars().all()
    return {
        "entries": [
            {
                "id": a.id,
                "actor": a.actor,
                "action": a.action,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "detail": a.detail,
                "ip": a.ip,
                "created_at": a.created_at,
            }
            for a in rows
        ]
    }
