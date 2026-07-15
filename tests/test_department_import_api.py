"""API импорта кафедр из Excel."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
SVOD = ROOT / "samples" / "Информационные материалы" / "2023_god_priema_SVOD_po_UP_FGOS3.xlsx"


@pytest.mark.asyncio
async def test_import_departments_xlsx(db_session) -> None:
    if not SVOD.is_file():
        pytest.skip("sample SVOD xlsx missing")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with SVOD.open("rb") as fh:
            res = await client.post(
                "/api/v1/reference/departments/import/",
                files={"file": (SVOD.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] >= 20
    assert data["added"] + data["skipped"] == data["total"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with SVOD.open("rb") as fh:
            res2 = await client.post(
                "/api/v1/reference/departments/import/",
                files={"file": (SVOD.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["skipped"] == data2["total"]
    assert data2["added"] == 0
