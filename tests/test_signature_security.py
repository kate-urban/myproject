"""Защита приватных файлов подписей от прямой загрузки."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_static_signatures_path_is_blocked() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/static/signatures/example.png")
    assert res.status_code == 403
