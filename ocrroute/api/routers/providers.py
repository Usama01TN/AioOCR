"""Providers & credentials CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ocrroute.api.deps import db_session
from ocrroute.api.schemas.common import CredentialCreate, ProviderCreate, ProviderUpdate
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.crypto import SecretBox, new_ulid
from ocrroute.db.models import Credential, Provider
from ocrroute.errors import ErrorCode

router = APIRouter(tags=["providers"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@router.get("/providers")
async def list_providers(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    rows = (
        (await session.execute(select(Provider).options(selectinload(Provider.credentials))))
        .scalars()
        .all()
    )
    box = SecretBox()
    return {
        "providers": [
            {
                "id": p.id,
                "engine_id": p.engine_id,
                "label": p.label,
                "enabled": p.enabled,
                "priority": p.priority,
                "weight": p.weight,
                "endpoint": p.endpoint,
                "model": p.model,
                "language": p.language,
                "timeout": p.timeout,
                "retries": p.retries,
                "options": p.options,
                "health": p.health,
                "circuit_open_until": p.circuit_open_until,
                "consecutive_failures": p.consecutive_failures,
                "credentials": [
                    {
                        "id": c.id,
                        "alias": c.alias,
                        "masked": box.mask(box.decrypt(c.secret_enc)) if c.secret_enc else "",
                        "enabled": c.enabled,
                        "order_index": c.order_index,
                        "success_count": c.success_count,
                        "failure_count": c.failure_count,
                        "exhausted_until": c.exhausted_until,
                    }
                    for c in p.credentials
                ],
            }
            for p in rows
        ]
    }


@router.post("/providers")
async def create_provider(
    body: ProviderCreate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    p = Provider(
        id=new_ulid(),
        engine_id=body.engine_id,
        label=body.label,
        enabled=body.enabled,
        priority=body.priority,
        weight=body.weight,
        endpoint=body.endpoint,
        model=body.model,
        language=body.language,
        timeout=body.timeout,
        retries=body.retries,
        options=body.options,
        proxy=body.proxy,
        concurrency_limit=body.concurrency_limit,
        rpm_limit=body.rpm_limit,
        rpd_limit=body.rpd_limit,
        monthly_budget_cents=body.monthly_budget_cents,
        notes=body.notes,
    )
    session.add(p)
    await session.flush()
    return {"id": p.id, "label": p.label}


@router.patch("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    p = await session.get(Provider, provider_id)
    if not p:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = _utcnow()
    return {"id": p.id, "label": p.label}


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, str]:
    p = await session.get(Provider, provider_id)
    if not p:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    await session.delete(p)
    return {"status": "deleted"}


@router.post("/providers/{provider_id}/reset-circuit")
async def reset_circuit(
    provider_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    p = await session.get(Provider, provider_id)
    if not p:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    p.circuit_open_until = None
    p.consecutive_failures = 0
    p.health = "unknown"
    return {"id": p.id, "health": p.health}


@router.post("/credentials")
async def create_credential(
    body: CredentialCreate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    box = SecretBox()
    c = Credential(
        id=new_ulid(),
        provider_id=body.provider_id,
        alias=body.alias,
        secret_enc=box.encrypt(body.secret),
        enabled=body.enabled,
        order_index=body.order_index,
    )
    session.add(c)
    await session.flush()
    return {"id": c.id, "alias": c.alias, "masked": box.mask(body.secret)}


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, str]:
    c = await session.get(Credential, credential_id)
    if not c:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    await session.delete(c)
    return {"status": "deleted"}
