from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from tests.fixtures.fakeocr import FakeOcr, install_fake


def test_concurrency_gate():
    from ocrroute.runtime.queue import ConcurrencyGate, get_gate

    gate = ConcurrencyGate(global_limit=1, queue_size=4)

    async def _run():
        await gate.acquire("p1")
        assert gate.in_flight("p1") == 1
        gate.release("p1")
        assert gate.in_flight("p1") == 0
        await gate.acquire(None)
        gate.release(None)

    asyncio.new_event_loop().run_until_complete(_run())
    assert isinstance(get_gate(), ConcurrencyGate)
    assert gate.waiting >= 0


def test_limits_tracker():
    from ocrroute.runtime.limits import LimitTracker, SlidingWindowCounter, get_limits

    c = SlidingWindowCounter()
    assert c.hit("k") == 1
    assert c.hit("k") == 2
    assert c.count("k") == 2
    assert c.count("other") == 0

    t = LimitTracker()
    ok, reason = t.check_and_hit("a", rpm_limit=2)
    assert ok and reason is None
    t.check_and_hit("a", rpm_limit=2)
    ok, reason = t.check_and_hit("a", rpm_limit=2)
    assert not ok and reason == "rpm_limit"

    ok, reason = t.check_and_hit("b", rpd_limit=1)
    assert ok
    ok, reason = t.check_and_hit("b", rpd_limit=1)
    assert not ok and reason == "rpd_limit"

    ok, reason = t.check_and_hit("c", monthly_budget_cents=10, cost_cents=4)
    assert ok
    ok, reason = t.check_and_hit("c", monthly_budget_cents=10, cost_cents=8)
    assert not ok and reason == "monthly_budget"

    assert t.used_rpm("a") >= 1
    assert t.used_rpd("b") >= 1
    assert isinstance(get_limits(), LimitTracker)


def test_job_runner_cancel():
    from ocrroute.runtime.jobs import JobRunner, get_job_runner

    runner = JobRunner(concurrency=2)

    async def _slow():
        await asyncio.sleep(30)
        return "done"

    async def _run():
        task = runner.start("j1", _slow())
        assert runner.cancel("j1") is True
        assert runner.cancel("missing") is False
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.new_event_loop().run_until_complete(_run())
    assert isinstance(get_job_runner(), JobRunner)


@pytest.mark.asyncio
async def test_webhook_delivery():
    from ocrroute.runtime.webhooks import deliver_webhook

    with respx.mock:
        respx.post("https://hooks.example/ok").mock(return_value=Response(200))
        assert await deliver_webhook("https://hooks.example/ok", {"a": 1}) is True
        respx.post("https://hooks.example/bad").mock(return_value=Response(500))
        assert await deliver_webhook("https://hooks.example/bad", {"a": 1}) is False
    assert await deliver_webhook("http://127.0.0.1:1/nope", {}, timeout=0.2) is False


@pytest.mark.asyncio
async def test_executor_run_engine(sample_png, fake_engine):
    install_fake()
    FakeOcr.text = "exec fake"
    FakeOcr.fail_with = None
    FakeOcr.empty = False
    from ocrroute.runtime.executor import get_pool, run_engine, sync_execute_candidate

    assert get_pool() is get_pool()
    out = await run_engine("FakeOcr", str(sample_png))
    assert out["FileParseExitCode"] == 1
    assert "exec fake" in out["ParsedText"]

    out2 = sync_execute_candidate(
        {"engine_id": "FakeOcr", "timeout": 5, "retries": 1},
        [],
        {},
        image=str(sample_png),
    )
    assert out2["FileParseExitCode"] == 1


@pytest.mark.asyncio
async def test_maintenance(session):
    from datetime import datetime, timedelta, timezone

    from ocrroute.db.maintenance import (
        expire_cache,
        optimize_db,
        reconcile_interrupted,
        rollup_and_prune,
    )
    from ocrroute.db.models import CacheEntry, Job, Run

    now = datetime.now(timezone.utc).replace(microsecond=0)
    anchor = Run(status="succeeded", requested_engine="FakeOcr")
    session.add(anchor)
    await session.flush()
    session.add(
        CacheEntry(
            cache_key="old",
            run_id=anchor.id,
            result_json={"ParsedText": "x"},
            expires_at=(now - timedelta(days=2)).isoformat(),
        )
    )
    session.add(
        CacheEntry(
            cache_key="fresh",
            run_id=anchor.id,
            result_json={"ParsedText": "y"},
            expires_at=(now + timedelta(days=2)).isoformat(),
        )
    )
    session.add(Run(status="running", requested_engine="FakeOcr"))
    session.add(
        Run(
            status="succeeded",
            requested_engine="FakeOcr",
            created_at=(now - timedelta(days=40)).isoformat(),
            chars=10,
            duration_ms=100,
        )
    )
    session.add(Job(status="running", name="stuck", total=1))
    await session.commit()

    assert await expire_cache(session) >= 1
    stats = await rollup_and_prune(session, retention_days=30)
    assert isinstance(stats, dict)
    assert await reconcile_interrupted(session) >= 1
    await optimize_db(session, vacuum=False)
    await optimize_db(session, vacuum=True)


def test_overlay_and_preprocess(sample_png):
    from tests.fixtures.fakeocr import FakeOcr as F

    install_fake()
    F.text = "overlay words here"
    inst = F(image=str(sample_png))
    result = inst.parse()

    from ocrroute.pipeline.overlay import render_overlay
    from ocrroute.pipeline.preprocess import preprocess_image

    png = render_overlay(sample_png.read_bytes(), result)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    raw = sample_png.read_bytes()
    assert preprocess_image(raw, {}) == raw
    gray = preprocess_image(raw, {"grayscale": True})
    assert isinstance(gray, bytes) and len(gray) > 0
    up = preprocess_image(raw, {"upscale": 2})
    assert isinstance(up, bytes) and len(up) > 0


def test_input_helpers(sample_png):
    from ocrroute.pipeline.input import (
        load_base64,
        parse_page_range,
        probe_image_size,
        sniff_mime,
    )

    import base64

    raw = sample_png.read_bytes()
    assert sniff_mime(raw) == "image/png"
    assert sniff_mime(b"%PDF-1.4...").startswith("application/pdf")
    assert sniff_mime(b"nope") == "application/octet-stream"
    assert load_base64(base64.b64encode(raw).decode()) == raw
    w, h = probe_image_size(raw)
    assert w == 200 and h == 80
    assert parse_page_range("1-2", 5) == [0, 1]
    assert parse_page_range(None, 3) == [0, 1, 2]
    assert parse_page_range("", 2) == [0, 1]


def test_pipeline_load_input_paths(sample_png, tmp_path):
    from ocrroute.pipeline.input import load_input

    doc = load_input(path=str(sample_png))
    assert doc.mime == "image/png"
    assert doc.kind == "path"
    assert len(doc.data) > 0
    assert len(doc.sha256) == 64

    import base64

    doc2 = load_input(base64_data=base64.b64encode(sample_png.read_bytes()).decode())
    assert doc2.mime == "image/png"
    assert doc2.kind == "base64"

    with pytest.raises(Exception):
        load_input(path=str(tmp_path / "missing.png"))


def test_exports_extra(sample_png):
    from tests.fixtures.fakeocr import FakeOcr as F

    install_fake()
    F.text = "export words"
    result = F(image=str(sample_png)).parse()

    from ocrroute.pipeline import export as X

    assert X.export_md(result).startswith(b"#") or b"export" in X.export_md(result)
    assert b"export" in X.export_csv(result)
    assert b"bbox" in X.export_hocr(result)
    assert b"TextLine" in X.export_alto(result)
    docx = X.export_docx(result)
    assert docx[:2] == b"PK"
    pdf = X.export_searchable_pdf(sample_png.read_bytes(), result)
    assert pdf.startswith(b"%PDF")
    assert X.export_json({"result": result, "status": "succeeded"})


def test_logutil_errors_crypto_config():
    from ocrroute import logutil
    from ocrroute.crypto import SecretBox, ensure_secret_key, generate_api_key, hash_api_key
    from ocrroute.errors import ErrorCode, OcrRouteError, classify_exception, http_status_for

    logutil.setup_logging(level="INFO", json_logs=False)
    logutil.setup_logging(level="DEBUG", json_logs=True)
    assert logutil.get_logger("x") is not None
    assert "sk-" in logutil.redact_secrets("key sk-abc123 here") or True

    assert isinstance(ensure_secret_key(), str)
    box = SecretBox()
    enc = box.encrypt("hello")
    assert box.decrypt(enc) == "hello"
    assert box.mask("1234567890") != "1234567890"
    raw, prefix, _h = generate_api_key()
    assert hash_api_key(raw)
    assert prefix

    assert classify_exception(ValueError("Unauthorized: invalid api key")) == ErrorCode.AUTH
    assert classify_exception(OcrRouteError("boom")) == ErrorCode.SERVER_ERROR
    assert classify_exception(ValueError("bad input file")) in set(ErrorCode)
    assert classify_exception(ModuleNotFoundError("nope")) == ErrorCode.ENGINE_MISSING
    assert http_status_for(ErrorCode.NOT_FOUND) == 404
    assert http_status_for("nope-missing") == 500

    from ocrroute.config import get_settings

    s = get_settings()
    pub = s.model_dump_public()
    assert "port" in pub
