"""The browser shell is public, inert, local-only and independent of personal state."""

import asyncio

import httpx
from test_private import no_store_access, snapshot

from jarvis.api import create_app


def test_web_shell_assets_do_not_read_or_change_saved_state(service, engine, monkeypatch):
    before = snapshot(engine)

    async def request():
        app = create_app(service)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://jarvis.test"
            ) as client,
        ):
            for path, content_type in (
                ("/", "text/html"),
                ("/assets/app.js", "javascript"),
                ("/assets/app.css", "text/css"),
                ("/assets/icon.svg", "image/svg+xml"),
            ):
                result = await client.get(path, headers={"X-Jarvis-Mode": "private"})
                assert result.status_code == 200
                assert content_type in result.headers["Content-Type"]
                assert result.headers["Cache-Control"] == "no-store"
                assert result.headers["X-Content-Type-Options"] == "nosniff"
                assert result.headers["Referrer-Policy"] == "no-referrer"
                assert result.headers["X-Frame-Options"] == "DENY"
                assert "frame-ancestors 'none'" in result.headers["Content-Security-Policy"]
                assert "unsafe-inline" not in result.headers["Content-Security-Policy"]
                assert "set-cookie" not in result.headers
            for path in ("/assets/.env", "/assets/%2e%2e/config.py"):
                assert (await client.get(path)).status_code == 404

    with no_store_access(engine, monkeypatch):
        asyncio.run(request())
    assert snapshot(engine) == before
