from __future__ import annotations

import base64

import pytest

from tests.fixtures.fakeocr import FakeOcr, install_fake


async def _sync(session):
    from ocrroute.runtime.service import OcrService

    await OcrService().ensure_engines_synced(session)
    await session.commit()


@pytest.mark.asyncio
async def test_providers_crud(client, session, fake_engine):
    install_fake()
    await _sync(session)

    r = await client.get("/v1/providers")
    assert r.status_code == 200
    assert "providers" in r.json()

    r = await client.post("/v1/providers", json={"engine_id": "FakeOcr", "label": "mgmt-p1"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    r = await client.patch(f"/v1/providers/{pid}", json={"label": "mgmt-p1b", "priority": 5})
    assert r.status_code == 200
    assert r.json()["label"] == "mgmt-p1b"

    r = await client.post(f"/v1/providers/{pid}/reset-circuit")
    assert r.status_code == 200
    assert r.json()["health"] == "unknown"

    r = await client.patch("/v1/providers/nope", json={"label": "x"})
    assert r.status_code == 404
    r = await client.delete("/v1/providers/nope")
    assert r.status_code == 404
    r = await client.post("/v1/providers/nope/reset-circuit")
    assert r.status_code == 404

    r = await client.delete(f"/v1/providers/{pid}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_credentials_crud(client, session, fake_engine):
    install_fake()
    await _sync(session)
    r = await client.post("/v1/providers", json={"engine_id": "FakeOcr", "label": "mgmt-cred"})
    pid = r.json()["id"]

    r = await client.post(
        "/v1/credentials",
        json={"provider_id": pid, "alias": "k1", "secret": "supersecretvalue"},
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert "masked" in r.json()

    r = await client.get("/v1/providers")
    provs = {p["id"]: p for p in r.json()["providers"]}
    assert provs[pid]["credentials"], "credential should be listed"
    assert "supersecretvalue" not in r.text  # never leak plaintext

    r = await client.delete(f"/v1/credentials/{cid}")
    assert r.status_code == 200
    r = await client.delete("/v1/credentials/nope")
    assert r.status_code == 404
    await client.delete(f"/v1/providers/{pid}")


@pytest.mark.asyncio
async def test_routes_crud_and_simulate(client, session, fake_engine):
    install_fake()
    await _sync(session)
    r = await client.post("/v1/providers", json={"engine_id": "FakeOcr", "label": "mgmt-rp"})
    pid = r.json()["id"]

    r = await client.get("/v1/routes/strategies")
    assert r.status_code == 200
    assert "priority" in (r.json()["strategies"] or r.json())

    r = await client.post(
        "/v1/routes",
        json={
            "name": "mgmt-route",
            "strategy": "priority",
            "is_default": True,
            "members": [{"provider_id": pid}],
        },
    )
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    r = await client.get("/v1/routes")
    assert rid in {x["id"] for x in r.json()["routes"]}

    r = await client.get(f"/v1/routes/{rid}")
    assert r.status_code == 200
    r = await client.get("/v1/routes/nope")
    assert r.status_code == 404

    r = await client.patch(f"/v1/routes/{rid}", json={"description": "hello"})
    assert r.status_code == 200
    r = await client.patch("/v1/routes/nope", json={"description": "x"})
    assert r.status_code == 404

    r = await client.post(f"/v1/routes/{rid}/members", json={"provider_id": pid, "weight": 2})
    assert r.status_code == 200
    r = await client.post("/v1/routes/nope/members", json={"provider_id": pid})
    assert r.status_code == 404

    r = await client.post(f"/v1/routes/{rid}/simulate", json={"mime": "image/png", "pages": 1})
    assert r.status_code == 200, r.text
    assert "candidates" in r.json()
    r = await client.post("/v1/routes/nope/simulate", json={})
    assert r.status_code == 404

    # patch by name + second default flips first
    r = await client.post("/v1/routes", json={"name": "mgmt-route2", "is_default": True})
    assert r.status_code == 200
    rid2 = r.json()["id"]
    r = await client.patch("/v1/routes/mgmt-route2", json={"is_default": True})
    assert r.status_code == 200

    r = await client.delete(f"/v1/routes/{rid}")
    assert r.status_code == 200
    r = await client.delete("/v1/routes/nope")
    assert r.status_code == 404
    await client.delete(f"/v1/routes/{rid2}")
    await client.delete(f"/v1/providers/{pid}")


@pytest.mark.asyncio
async def test_keys_flow_with_cleanup(client, session):
    from ocrroute.db.models import ApiKey

    r = await client.get("/v1/keys")
    assert r.status_code == 200

    r = await client.post(
        "/v1/keys", json={"name": "mgmt-key", "scopes": ["admin", "ocr:read", "ocr:write"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    kid = body["id"]
    raw = body.get("key") or body.get("api_key") or body.get("secret")
    assert raw, f"expected plaintext key in {body}"
    hdr = {"X-API-Key": raw}
    try:
        # Authenticated call with the new key
        r = await client.get("/v1/engines", headers=hdr)
        assert r.status_code == 200

        # Invalid key rejected now that a key exists
        r = await client.get("/v1/engines", headers={"X-API-Key": "bogus"})
        assert r.status_code == 401

        r = await client.post("/v1/keys/nope/revoke", headers=hdr)
        assert r.status_code == 404
        r = await client.delete("/v1/keys/nope", headers=hdr)
        assert r.status_code == 404

        r = await client.post(f"/v1/keys/{kid}/revoke", headers=hdr)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        r = await client.get("/v1/engines", headers=hdr)
        assert r.status_code == 401
    finally:
        # Hard delete via DB restores bootstrap (keyless) mode for other tests
        row = await session.get(ApiKey, kid)
        if row is not None:
            await session.delete(row)
            await session.commit()

    r = await client.get("/v1/engines")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_ocr_async_and_jobs(client, session, sample_png, fake_engine):
    install_fake()
    await _sync(session)
    FakeOcr.text = "async fake"
    FakeOcr.fail_with = None
    FakeOcr.empty = False

    blob = base64.b64encode(sample_png.read_bytes()).decode()
    r = await client.post("/v1/ocr/async", json={"base64": blob, "engine": "FakeOcr"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    r = await client.get(f"/v1/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert len(r.json()["items"]) == 1

    r = await client.get("/v1/jobs/nope")
    assert r.status_code == 404
    r = await client.post("/v1/jobs/nope/cancel")
    assert r.status_code == 404

    r = await client.post(f"/v1/jobs/{job_id}/cancel")
    assert r.status_code in (200, 409)


@pytest.mark.asyncio
async def test_runs_flow(client, session, sample_png, fake_engine):
    install_fake()
    await _sync(session)
    FakeOcr.text = "runs fake"
    FakeOcr.fail_with = None
    FakeOcr.empty = False

    with sample_png.open("rb") as fh:
        r = await client.post(
            "/v1/ocr",
            files={"file": ("sample.png", fh, "image/png")},
            data={"engine": "FakeOcr"},
        )
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r = await client.get("/v1/runs", params={"engine": "FakeOcr", "limit": 5})
    assert r.status_code == 200
    assert any(x["id"] == run_id for x in r.json()["runs"])

    r = await client.get(f"/v1/runs/{run_id}")
    assert r.status_code == 200
    r = await client.get("/v1/runs/nope")
    assert r.status_code == 404

    r = await client.get(f"/v1/runs/{run_id}/artifacts/text")
    assert r.status_code in (200, 404)
    r = await client.get(f"/v1/runs/{run_id}/overlay.png")
    assert r.status_code in (200, 404)
    r = await client.get("/v1/runs/nope/overlay.png")
    assert r.status_code == 404

    # Retry a run stored with base64 input
    from ocrroute.db.models import Run

    blob = base64.b64encode(sample_png.read_bytes()).decode()
    row = Run(
        status="failed",
        requested_engine="FakeOcr",
        language="en",
        metadata_json={"base64": blob},
    )
    session.add(row)
    await session.commit()
    r = await client.post(f"/v1/runs/{row.id}/retry")
    assert r.status_code == 200, r.text
    r = await client.post("/v1/runs/nope/retry")
    assert r.status_code == 404

    r = await client.delete(f"/v1/runs/{row.id}")
    assert r.status_code == 200
    r = await client.delete("/v1/runs/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_usage_stats_settings_system(client, session):
    r = await client.get("/v1/usage")
    assert r.status_code == 200
    assert "rows" in r.json()

    r = await client.get("/v1/stats/summary")
    assert r.status_code == 200
    assert "runs_total" in r.json() or "runs" in r.json()

    r = await client.get("/v1/settings")
    assert r.status_code == 200
    assert "overrides" in r.json()

    r = await client.put("/v1/settings/mgmt_note", json={"value": "hello"})
    assert r.status_code == 200
    r = await client.get("/v1/settings")
    assert r.json()["overrides"].get("mgmt_note") == "hello"

    r = await client.get("/v1/audit")
    assert r.status_code == 200
    assert any(e["action"] == "settings.set" for e in r.json()["entries"])

    r = await client.get("/v1/ready")
    assert r.status_code == 200

    r = await client.get("/v1/doctor")
    assert r.status_code == 200
    assert "database" in r.json()

    r = await client.get("/v1/metrics")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_engines_manage(client, session, fake_engine):
    install_fake()
    r = await client.post("/v1/engines/refresh")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    # refresh() force-rediscovers, dropping fakes — reinstall + sync
    install_fake()
    await _sync(session)

    r = await client.post("/v1/engines/FakeOcr/enable", params={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    r = await client.post("/v1/engines/FakeOcr/enable", params={"enabled": True})
    assert r.json()["enabled"] is True
    r = await client.post("/v1/engines/nope/enable")
    assert r.status_code == 404

    FakeOcr.text = "probe me"
    FakeOcr.fail_with = None
    FakeOcr.empty = False
    r = await client.post("/v1/engines/FakeOcr/probe")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = await client.post("/v1/engines/nope/probe")
    assert r.status_code == 200
    assert r.json()["ok"] is False


@pytest.mark.asyncio
async def test_batch_flow(client, session, sample_png, fake_engine):
    install_fake()
    await _sync(session)
    FakeOcr.text = "batch fake"
    FakeOcr.fail_with = None
    FakeOcr.empty = False

    r = await client.post(
        "/v1/batch",
        json={
            "name": "mgmt-batch",
            "engine": "FakeOcr",
            "items": [{"path": str(sample_png)}],
        },
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    r = await client.get(f"/v1/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = await client.post(f"/v1/jobs/{job_id}/cancel")
    assert r.status_code in (200, 409)
