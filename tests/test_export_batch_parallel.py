"""Тесты ограничения параллелизма пакетного экспорта."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.services.export_service import (
    _PackageDisciplineResult,
    _PackageFile,
    export_direction_year_package,
)


@pytest.mark.asyncio
async def test_export_batch_parallel_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("EXPORT_BATCH_MAX_PARALLEL", "2")

    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def fake_export(**kwargs) -> _PackageDisciplineResult:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.04)
        async with lock:
            active -= 1
        disc_id = kwargs.get("discipline_id", uuid.uuid4())
        return _PackageDisciplineResult(
            exported=1,
            files=[_PackageFile(arcname=f"RPD/{disc_id}.pdf", content=b"%PDF-1.4")],
        )

    import app.services.export_service as export_service

    monkeypatch.setattr(export_service, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(export_service, "_export_package_discipline", fake_export)

    async def _no_signatures(db):
        return []

    monkeypatch.setattr(
        "app.services.pdf_export.load_active_signatures",
        _no_signatures,
    )

    plan_id = uuid.uuid4()
    discipline_ids = [uuid.uuid4() for _ in range(6)]
    plan = type("Plan", (), {"id": plan_id})()

    class _FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return _FakeScalars(self._items)

    async def fake_execute(stmt):
        compiled = str(stmt).lower()
        if "plan_disciplines" in compiled:
            return _FakeResult(discipline_ids)
        return _FakeResult([plan])

    class _FakeDb:
        async def execute(self, stmt):
            return await fake_execute(stmt)

    zip_path, meta = await export_direction_year_package(
        _FakeDb(),
        direction_code="54.04.01",
        year=2026,
        force=True,
    )

    assert peak <= 2
    assert meta["exported"] == 6
    assert zip_path.endswith("package_54.04.01_2026.zip")
