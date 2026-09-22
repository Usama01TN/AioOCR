"""Async SQLAlchemy engine / session factory."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ocrroute.config import Settings, get_settings
from ocrroute.db.base import SQLITE_PRAGMAS, Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _apply_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
    cursor = dbapi_conn.cursor()
    for pragma in SQLITE_PRAGMAS:
        try:
            cursor.execute(pragma)
        except Exception:
            pass
    cursor.close()


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    settings = settings or get_settings()
    settings.ensure_dirs()
    _engine = create_async_engine(
        settings.async_database_url,
        echo=False,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(_engine.sync_engine, "connect")
    def _on_connect(dbapi_conn: Any, connection_record: Any) -> None:  # noqa: ARG001
        _apply_pragmas(dbapi_conn, connection_record)

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        get_engine(settings)
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(settings: Settings | None = None) -> None:
    """Create all tables (dev/bootstrap). Alembic is preferred in production."""
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for pragma in SQLITE_PRAGMAS:
            try:
                await conn.execute(text(pragma))
            except Exception:
                pass


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_engine() -> None:
    """Synchronous reset used by tests."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
