from __future__ import annotations

import pytest

PAGES = [
    "/panel/",
    "/panel/engines",
    "/panel/providers",
    "/panel/routes",
    "/panel/playground",
    "/panel/runs",
    "/panel/usage",
    "/panel/keys",
    "/panel/batch",
    "/panel/tools",
    "/panel/settings",
    "/panel/doctor",
    "/panel/login",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PAGES)
async def test_panel_pages_ok(client, path):
    r = await client.get(path)
    assert r.status_code == 200, path
    assert b"<html" in r.content


@pytest.mark.asyncio
async def test_panel_login_flow(client):
    # First login creates the admin user
    r = await client.post(
        "/panel/login",
        data={"username": "paneladmin", "password": "s3cret-pw"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    # Wrong password rejected
    r = await client.post(
        "/panel/login",
        data={"username": "paneladmin", "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert "error=1" in r.headers.get("location", "")

    # Unknown user rejected (admin already exists)
    r = await client.post(
        "/panel/login",
        data={"username": "ghost", "password": "x"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    # Correct login works
    r = await client.post(
        "/panel/login",
        data={"username": "paneladmin", "password": "s3cret-pw"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r = await client.get("/panel/logout", follow_redirects=False)
    assert r.status_code in (302, 303)


@pytest.mark.asyncio
async def test_panel_prefs_and_cookies(client):
    r = await client.get("/panel/prefs?lang=fr&theme=dark&next=/panel/", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.cookies.get("ocrroute_lang") == "fr"
    assert r.cookies.get("ocrroute_theme") == "dark"

    # Open redirect guarded
    r = await client.get("/panel/prefs?next=https://evil.example/", follow_redirects=False)
    assert r.headers.get("location", "").startswith("/panel")

    r = await client.get("/panel/?lang=de")
    assert r.status_code == 200
    assert b"lang=\"de\"" in r.content or "Übersicht".encode() in r.content
