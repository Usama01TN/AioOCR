from __future__ import annotations

import pytest

from tests.fixtures.fakeocr import FakeOcr, install_fake


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_version(client):
    r = await client.get("/v1/version")
    assert r.status_code == 200
    assert "version" in r.json()


@pytest.mark.asyncio
async def test_tools_reserved(client):
    r = await client.get("/v1/tools")
    assert r.status_code == 200
    body = r.json()
    assert body["tools"] == []
    assert body["reserved"] is True

    r = await client.get("/v1/tools/nope")
    assert r.status_code == 404

    r = await client.post("/v1/tools/nope/run")
    assert r.status_code == 501
    assert r.json()["detail"]["error_code"] == "tools_reserved"


@pytest.mark.asyncio
async def test_engines_list(client, fake_engine):
    install_fake()
    r = await client.get("/v1/engines")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["engines"]}
    # At least the discovered catalogue (may include unavailable)
    assert len(ids) >= 1


@pytest.mark.asyncio
async def test_ocr_with_fake(client, sample_png, fake_engine, session):
    install_fake()
    FakeOcr.text = "hello from fake"
    FakeOcr.fail_with = None
    FakeOcr.empty = False

    # Ensure engine row exists
    from ocrroute.runtime.service import OcrService

    svc = OcrService()
    await svc.ensure_engines_synced(session)
    await session.commit()

    with sample_png.open("rb") as fh:
        r = await client.post(
            "/v1/ocr",
            files={"file": ("sample.png", fh, "image/png")},
            data={"engine": "FakeOcr"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("succeeded", "cached")
    assert body["result"]["FileParseExitCode"] == 1
    assert "fake" in body["result"]["ParsedText"].lower() or body["result"]["ParsedText"]
    assert "routing" in body
    assert body["run_id"]


@pytest.mark.asyncio
async def test_ocr_cache(client, sample_png, fake_engine, session):
    install_fake()
    FakeOcr.text = "cached text"
    from ocrroute.runtime.service import OcrService

    await OcrService().ensure_engines_synced(session)
    await session.commit()

    async def once():
        with sample_png.open("rb") as fh:
            return await client.post(
                "/v1/ocr",
                files={"file": ("sample.png", fh, "image/png")},
                data={"engine": "FakeOcr"},
            )

    r1 = await once()
    r2 = await once()
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("cached") is True or r2.json()["status"] == "cached"


@pytest.mark.asyncio
async def test_bad_path_via_service(session, fake_engine):
    install_fake()
    from ocrroute.errors import ErrorCode, OcrRouteError
    from ocrroute.runtime.service import OcrService

    svc = OcrService()
    await svc.ensure_engines_synced(session)
    with pytest.raises(OcrRouteError) as ei:
        await svc.run_ocr(session, path="/no/such/file.png", engine="FakeOcr")
    assert ei.value.code == ErrorCode.BAD_INPUT


@pytest.mark.asyncio
async def test_panel_tools_page(client):
    r = await client.get("/panel/tools")
    assert r.status_code == 200
    assert b"No tools are installed" in r.content


@pytest.mark.asyncio
async def test_panel_overview(client):
    r = await client.get("/panel/")
    assert r.status_code == 200
    assert b"Overview" in r.content


@pytest.mark.asyncio
async def test_panel_arabic_rtl(client):
    r = await client.get("/panel/?lang=ar")
    assert r.status_code == 200
    assert b'dir="rtl"' in r.content
    assert "نظرة عامة".encode("utf-8") in r.content


@pytest.mark.asyncio
async def test_panel_theme_dark(client):
    r = await client.get("/panel/?theme=dark")
    assert r.status_code == 200
    assert b'data-theme="dark"' in r.content
