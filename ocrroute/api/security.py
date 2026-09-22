"""API key auth and scope checks."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.crypto import hash_api_key
from ocrroute.db.models import ApiKey
from ocrroute.db.session import get_session_factory
from ocrroute.errors import ErrorCode


async def _session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


class AuthContext:
    def __init__(
        self,
        api_key: ApiKey | None = None,
        *,
        is_admin: bool = False,
        scopes: list[str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.is_admin = is_admin
        self.scopes = scopes or (api_key.scopes if api_key else []) or []

    @property
    def key_id(self) -> str | None:
        return self.api_key.id if self.api_key else None

    @property
    def route_id(self) -> str | None:
        return self.api_key.route_id if self.api_key else None

    def require(self, scope: str) -> None:
        if self.is_admin:
            return
        if "admin" in self.scopes:
            return
        if scope not in self.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": ErrorCode.FORBIDDEN.value,
                    "error_message": f"Missing scope: {scope}",
                },
            )


async def get_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    # Dev/bootstrap: if no keys exist yet, allow unauthenticated local access with admin
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif x_api_key:
        raw = x_api_key.strip()

    factory = get_session_factory()
    async with factory() as session:
        if not raw:
            # Check if any keys exist
            count = (await session.execute(select(ApiKey).limit(1))).scalar_one_or_none()
            if count is None:
                return AuthContext(is_admin=True, scopes=["admin", "ocr:read", "ocr:write"])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": ErrorCode.AUTH.value, "error_message": "Missing API key"},
            )

        key_hash = hash_api_key(raw)
        row = (
            await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        ).scalar_one_or_none()
        if row is None or not row.enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": ErrorCode.AUTH.value, "error_message": "Invalid API key"},
            )
        if row.expires_at:
            try:
                exp = datetime.fromisoformat(row.expires_at.replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={
                            "error_code": ErrorCode.AUTH.value,
                            "error_message": "API key expired",
                        },
                    )
            except ValueError:
                pass
        row.last_used_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        await session.commit()
        scopes = list(row.scopes or [])
        return AuthContext(api_key=row, is_admin="admin" in scopes, scopes=scopes)


def require_scope(scope: str):
    async def _dep(auth: AuthContext = Depends(get_auth)) -> AuthContext:
        auth.require(scope)
        return auth

    return _dep
