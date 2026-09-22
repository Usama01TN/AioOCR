"""Shared fixtures."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import ocrroute.db.models  # noqa: F401  (register models before init_db)

# Isolate all test data
@pytest.fixture(scope="session", autouse=True)
def _test_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("ocrroute-home")
    os.environ["OCRROUTE_HOME"] = str(home)
    os.environ["OCRROUTE_SECRET_KEY"] = "test-secret-key-not-for-production-use-32b"
    os.environ["OCRROUTE_LOG_JSON"] = "false"
    from ocrroute.config import reset_settings_cache
    from ocrroute.db.session import reset_engine
    from ocrroute.catalog.registry import reset_registry

    reset_settings_cache()
    reset_engine()
    reset_registry()
    yield home
    reset_settings_cache()
    reset_engine()
    reset_registry()


@pytest_asyncio.fixture
async def app(_test_home):
    from ocrroute.api.app import create_app
    from ocrroute.config import get_settings, reset_settings_cache
    from ocrroute.db.session import init_db, reset_engine, dispose_db

    reset_settings_cache()
    reset_engine()
    settings = get_settings()
    application = create_app(settings)
    await init_db(settings)
    yield application
    await dispose_db()
    reset_engine()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session(_test_home):
    from ocrroute.config import get_settings, reset_settings_cache
    from ocrroute.db.session import get_session_factory, init_db, reset_engine, dispose_db

    reset_settings_cache()
    reset_engine()
    settings = get_settings()
    await init_db(settings)
    factory = get_session_factory(settings)
    async with factory() as s:
        yield s
        await s.commit()
    await dispose_db()
    reset_engine()


@pytest.fixture
def sample_png(tmp_path) -> Path:
    from PIL import Image, ImageDraw

    path = tmp_path / "sample.png"
    img = Image.new("RGB", (200, 80), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 30), "Hello OcrRoute", fill="black")
    img.save(path)
    return path


@pytest.fixture
def fake_engine(monkeypatch):
    """Register FakeOcr in the registry for tests."""
    from tests.fixtures.fakeocr import FakeOcr, install_fake

    return install_fake()
