from __future__ import annotations

from typer.testing import CliRunner

from ocrroute.cli.main import app
from tests.fixtures.fakeocr import FakeOcr, install_fake

runner = CliRunner()


def test_cli_version():
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["version", "--json"])
    assert r.exit_code == 0, r.output
    assert "version" in r.output


def test_cli_engines(fake_engine):
    install_fake()
    r = runner.invoke(app, ["engines", "list"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["engines", "list", "--json"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["engines", "refresh"])
    assert r.exit_code == 0, r.output
    install_fake()  # refresh() force-rediscovers, dropping fakes
    r = runner.invoke(app, ["engines", "options", "FakeOcr"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["engines", "options", "NopeMissing"])
    assert r.exit_code == 1


def test_cli_lists_smoke():
    for args in (
        ["provider", "list"],
        ["route", "list"],
        ["runs", "list"],
        ["config", "export"],
    ):
        r = runner.invoke(app, args)
        assert r.exit_code == 0, (args, r.output)


def test_cli_config_get():
    r = runner.invoke(app, ["config", "get", "port"])
    assert r.exit_code == 0, r.output
    assert "20256" in r.output


def test_cli_db_commands(tmp_path):
    r = runner.invoke(app, ["db", "migrate"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["db", "integrity"])
    assert r.exit_code == 0, r.output
    assert "ok" in r.output.lower()
    r = runner.invoke(app, ["db", "vacuum"])
    assert r.exit_code == 0, r.output

    dest = tmp_path / "backup.db"
    r = runner.invoke(app, ["db", "backup", str(dest)])
    assert r.exit_code == 0, r.output
    assert dest.exists()
    r = runner.invoke(app, ["db", "restore", str(dest)])
    assert r.exit_code == 0, r.output


def test_cli_key_flow_with_cleanup():
    import asyncio

    from sqlalchemy import select

    from ocrroute.db.models import ApiKey
    from ocrroute.db.session import get_session_factory, init_db

    async def _rows():
        await init_db()
        factory = get_session_factory()
        async with factory() as s:
            rows = (await s.execute(select(ApiKey))).scalars().all()
            return [(k.id, k.name) for k in rows]

    async def _delete(kid):
        await init_db()
        factory = get_session_factory()
        async with factory() as s:
            row = await s.get(ApiKey, kid)
            if row is not None:
                await s.delete(row)
                await s.commit()

    r = runner.invoke(app, ["key", "create", "--name", "cli-key"])
    assert r.exit_code == 0, r.output

    r = runner.invoke(app, ["key", "list"])
    assert r.exit_code == 0, r.output
    assert "cli-key" in r.output
    r = runner.invoke(app, ["key", "list", "--json"])
    assert r.exit_code == 0, r.output

    rows = asyncio.run(_rows())
    mine = [i for i, n in rows if n == "cli-key"]
    assert mine, "cli key row should exist"

    r = runner.invoke(app, ["key", "revoke", mine[0]])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["key", "revoke", "missing-id"])
    assert r.exit_code == 1

    # Hard-delete to restore keyless bootstrap mode for other tests
    asyncio.run(_delete(mine[0]))
    rows = asyncio.run(_rows())
    assert not [i for i, n in rows if n == "cli-key"]


def test_cli_ocr_and_batch(sample_png, fake_engine, tmp_path):
    install_fake()
    FakeOcr.text = "cli fake"
    FakeOcr.fail_with = None
    FakeOcr.empty = False

    r = runner.invoke(app, ["ocr", str(sample_png), "--engine", "FakeOcr"])
    assert r.exit_code == 0, r.output
    assert "cli fake" in r.output.lower() or "fake" in r.output.lower()

    r = runner.invoke(app, ["ocr", str(sample_png), "--engine", "FakeOcr", "--json"])
    assert r.exit_code == 0, r.output
    assert "ParsedText" in r.output or "parsed" in r.output.lower()

    d = tmp_path / "batchdir"
    d.mkdir()
    (d / "a.png").write_bytes(sample_png.read_bytes())
    r = runner.invoke(app, ["batch", str(d)])
    assert r.exit_code == 0, r.output
    assert "Batch:" in r.output
