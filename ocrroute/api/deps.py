"""FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ocrroute.config import Settings, get_settings
from ocrroute.db.session import get_session_factory
from ocrroute.runtime.service import OcrService


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def settings_dep() -> Settings:
    return get_settings()


def ocr_service(settings: Settings = None) -> OcrService:  # type: ignore[assignment]
    return OcrService(settings or get_settings())
