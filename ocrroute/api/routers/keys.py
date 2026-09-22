"""Client API key management."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.api.deps import db_session
from ocrroute.api.schemas.common import ApiKeyCreate
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.crypto import generate_api_key, new_ulid
from ocrroute.db.models import ApiKey
from ocrroute.errors import ErrorCode

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("")
async def list_keys(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    rows = (await session.execute(select(ApiKey))).scalars().all()
    return {
        "keys": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "scopes": k.scopes,
                "route_id": k.route_id,
                "enabled": k.enabled,
                "rpm_limit": k.rpm_limit,
                "rpd_limit": k.rpd_limit,
                "monthly_budget_cents": k.monthly_budget_cents,
                "expires_at": k.expires_at,
                "last_used_at": k.last_used_at,
                "created_at": k.created_at,
            }
            for k in rows
        ]
    }


@router.post("")
async def create_key(
    body: ApiKeyCreate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    raw, key_hash, prefix = generate_api_key()
    k = ApiKey(
        id=new_ulid(),
        name=body.name,
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=body.scopes,
        route_id=body.route_id,
        rpm_limit=body.rpm_limit,
        rpd_limit=body.rpd_limit,
        monthly_budget_cents=body.monthly_budget_cents,
        expires_at=body.expires_at,
    )
    session.add(k)
    await session.flush()
    return {
        "id": k.id,
        "name": k.name,
        "key": raw,  # shown once
        "key_prefix": prefix,
        "scopes": k.scopes,
    }


@router.post("/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    k = await session.get(ApiKey, key_id)
    if not k:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    k.enabled = False
    return {"id": k.id, "enabled": False}


@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, str]:
    k = await session.get(ApiKey, key_id)
    if not k:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    await session.delete(k)
    return {"status": "deleted"}
