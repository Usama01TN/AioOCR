"""Routes management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ocrroute.api.deps import db_session
from ocrroute.api.schemas.common import RouteCreate, RouteMemberCreate, RouteUpdate, SimulateRequest
from ocrroute.api.security import AuthContext, require_scope
from ocrroute.crypto import new_ulid
from ocrroute.db.models import Provider, Route, RouteMember
from ocrroute.errors import ErrorCode
from ocrroute.routing.router import simulate_route
from ocrroute.routing.strategies import list_strategies

router = APIRouter(prefix="/routes", tags=["routes"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@router.get("/strategies")
async def strategies(auth: AuthContext = Depends(require_scope("ocr:read"))) -> dict[str, Any]:
    return {"strategies": list_strategies()}


@router.get("")
async def list_routes(
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    rows = (
        (await session.execute(select(Route).options(selectinload(Route.members)))).scalars().all()
    )
    return {
        "routes": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "strategy": r.strategy,
                "enabled": r.enabled,
                "is_default": r.is_default,
                "member_count": len(r.members),
                "stop_condition": r.stop_condition,
                "max_attempts": r.max_attempts,
            }
            for r in rows
        ]
    }


@router.post("")
async def create_route(
    body: RouteCreate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    if body.is_default:
        existing = (
            (await session.execute(select(Route).where(Route.is_default.is_(True)))).scalars().all()
        )
        for e in existing:
            e.is_default = False
    r = Route(
        id=new_ulid(),
        name=body.name,
        description=body.description,
        strategy=body.strategy,
        enabled=body.enabled,
        is_default=body.is_default,
        stop_condition=body.stop_condition,
        max_attempts=body.max_attempts,
        total_deadline_ms=body.total_deadline_ms,
        cache_ttl_seconds=body.cache_ttl_seconds,
    )
    session.add(r)
    await session.flush()
    for i, m in enumerate(body.members):
        session.add(
            RouteMember(
                id=new_ulid(),
                route_id=r.id,
                provider_id=m["provider_id"],
                order_index=m.get("order_index", i),
                weight=m.get("weight", 1),
                enabled=m.get("enabled", True),
                condition=m.get("condition"),
                option_overrides=m.get("option_overrides"),
            )
        )
    await session.flush()
    return {"id": r.id, "name": r.name}


@router.get("/{route_id}")
async def get_route(
    route_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    r = (
        await session.execute(
            select(Route)
            .where((Route.id == route_id) | (Route.name == route_id))
            .options(selectinload(Route.members))
        )
    ).scalar_one_or_none()
    if not r:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "strategy": r.strategy,
        "enabled": r.enabled,
        "is_default": r.is_default,
        "stop_condition": r.stop_condition,
        "max_attempts": r.max_attempts,
        "total_deadline_ms": r.total_deadline_ms,
        "cache_ttl_seconds": r.cache_ttl_seconds,
        "members": [
            {
                "id": m.id,
                "provider_id": m.provider_id,
                "order_index": m.order_index,
                "weight": m.weight,
                "enabled": m.enabled,
                "condition": m.condition,
                "option_overrides": m.option_overrides,
            }
            for m in r.members
        ],
    }


@router.patch("/{route_id}")
async def update_route(
    route_id: str,
    body: RouteUpdate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    r = await session.get(Route, route_id)
    if not r:
        r = (
            await session.execute(select(Route).where(Route.name == route_id))
        ).scalar_one_or_none()
    if not r:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        existing = (
            (await session.execute(select(Route).where(Route.is_default.is_(True)))).scalars().all()
        )
        for e in existing:
            e.is_default = False
    for k, v in data.items():
        setattr(r, k, v)
    r.updated_at = _utcnow()
    return {"id": r.id, "name": r.name}


@router.delete("/{route_id}")
async def delete_route(
    route_id: str,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, str]:
    r = await session.get(Route, route_id)
    if not r:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    await session.delete(r)
    return {"status": "deleted"}


@router.post("/{route_id}/members")
async def add_member(
    route_id: str,
    body: RouteMemberCreate,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("admin")),
) -> dict[str, Any]:
    r = await session.get(Route, route_id)
    if not r:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    m = RouteMember(
        id=new_ulid(),
        route_id=r.id,
        provider_id=body.provider_id,
        order_index=body.order_index,
        weight=body.weight,
        enabled=body.enabled,
        condition=body.condition,
        option_overrides=body.option_overrides,
    )
    session.add(m)
    await session.flush()
    return {"id": m.id}


@router.post("/{route_id}/simulate")
async def simulate(
    route_id: str,
    body: SimulateRequest,
    session: AsyncSession = Depends(db_session),
    auth: AuthContext = Depends(require_scope("ocr:read")),
) -> dict[str, Any]:
    r = (
        await session.execute(
            select(Route)
            .where((Route.id == route_id) | (Route.name == route_id))
            .options(
                selectinload(Route.members)
                .selectinload(RouteMember.provider)
                .selectinload(Provider.engine)
            )
        )
    ).scalar_one_or_none()
    if not r:
        raise HTTPException(404, detail={"error_code": ErrorCode.NOT_FOUND.value})
    members = []
    for m in r.members:
        p = m.provider
        eng = p.engine if p else None
        members.append(
            {
                "provider_id": m.provider_id,
                "engine_id": p.engine_id if p else "?",
                "label": p.label if p else "?",
                "kind": eng.kind if eng else "api",
                "enabled": m.enabled and (p.enabled if p else False),
                "engine_available": bool(eng.available) if eng else False,
                "available": True,
                "order_index": m.order_index,
                "weight": m.weight,
                "condition": m.condition,
                "circuit_open_until": p.circuit_open_until if p else None,
                "cost_model": eng.cost_model if eng else "local",
                "unit_price": eng.unit_price if eng else 0,
                "quality_score": eng.quality_score if eng else 0.5,
                "languages": eng.languages if eng else [],
            }
        )
    ctx = {
        "mime": body.mime,
        "page_count": body.pages,
        "languages": (
            body.language
            if isinstance(body.language, list)
            else ([body.language] if body.language else [])
        ),
        "dimensions": (body.width, body.height),
        "handwriting": body.handwriting,
        "tables": body.tables,
        "sensitive": body.sensitive,
        "offline": body.offline,
    }
    return simulate_route(members, r.strategy, ctx)
