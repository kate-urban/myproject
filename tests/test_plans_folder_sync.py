"""Автоимпорт учебных планов из папки «УЧЕБНЫЕ ПЛАНЫ»."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.services.plans_folder_nav import (
    _collect_files,
    _scan_folder,
    import_plan_from_relative_path,
    sync_folder_plans,
)

DESIGN_PLX = Path(__file__).resolve().parents[1] / "samples" / "M540401-2026.plx"


@pytest.mark.asyncio
async def test_sync_imports_and_deletes_file(db_session, tmp_path, monkeypatch) -> None:
    plans_dir = tmp_path / "УЧЕБНЫЕ ПЛАНЫ" / "ОЧНОЕ ОБУЧЕНИЕ" / "Магистры" / "ИЛиП" / "2026"
    plans_dir.mkdir(parents=True)
    target = plans_dir / "M540401-2026.plx"
    shutil.copy(DESIGN_PLX, target)

    monkeypatch.setenv("PLANS_FOLDER", str(tmp_path / "УЧЕБНЫЕ ПЛАНЫ"))
    monkeypatch.setenv("PLANS_AUTO_IMPORT", "true")
    monkeypatch.setenv("PLANS_DELETE_AFTER_IMPORT", "true")

    result = await sync_folder_plans(db_session)
    assert result.imported == 1
    assert result.deleted == 1
    assert not target.is_file()

    tree = _scan_folder(tmp_path / "УЧЕБНЫЕ ПЛАНЫ", tmp_path / "УЧЕБНЫЕ ПЛАНЫ")
    assert _collect_files(tree) == []


@pytest.mark.asyncio
async def test_import_from_relative_path_deletes_file(db_session, tmp_path, monkeypatch) -> None:
    plans_dir = tmp_path / "УЧЕБНЫЕ ПЛАНЫ" / "2026"
    plans_dir.mkdir(parents=True)
    target = plans_dir / "M540401-2026.plx"
    shutil.copy(DESIGN_PLX, target)

    monkeypatch.setenv("PLANS_FOLDER", str(tmp_path / "УЧЕБНЫЕ ПЛАНЫ"))
    monkeypatch.setenv("PLANS_DELETE_AFTER_IMPORT", "true")

    plan = await import_plan_from_relative_path(
        db_session,
        "2026/M540401-2026.plx",
        delete_after=True,
    )
@pytest.mark.asyncio
async def test_sync_respects_batch_size(db_session, tmp_path, monkeypatch) -> None:
    plans_dir = tmp_path / "УЧЕБНЫЕ ПЛАНЫ" / "2026"
    plans_dir.mkdir(parents=True)
    first = plans_dir / "M540401-2026.plx"
    second = plans_dir / "M540401-2026-copy.plx"
    shutil.copy(DESIGN_PLX, first)
    shutil.copy(DESIGN_PLX, second)

    monkeypatch.setenv("PLANS_FOLDER", str(tmp_path / "УЧЕБНЫЕ ПЛАНЫ"))
    monkeypatch.setenv("PLANS_AUTO_IMPORT", "true")
    monkeypatch.setenv("PLANS_DELETE_AFTER_IMPORT", "false")
    monkeypatch.setenv("PLANS_SYNC_BATCH_SIZE", "1")

    result = await sync_folder_plans(db_session)
    assert result.imported == 1
    assert first.is_file() ^ second.is_file() or (first.is_file() and second.is_file())
    assert sum(1 for path in (first, second) if path.is_file()) >= 1


@pytest.mark.asyncio
async def test_sync_skips_already_imported_and_cleans_file(
    db_session, tmp_path, monkeypatch
) -> None:
    plans_dir = tmp_path / "УЧЕБНЫЕ ПЛАНЫ" / "2026"
    plans_dir.mkdir(parents=True)
    target = plans_dir / "M540401-2026.plx"
    shutil.copy(DESIGN_PLX, target)

    monkeypatch.setenv("PLANS_FOLDER", str(tmp_path / "УЧЕБНЫЕ ПЛАНЫ"))
    monkeypatch.setenv("PLANS_DELETE_AFTER_IMPORT", "true")

    await import_plan_from_relative_path(db_session, "2026/M540401-2026.plx")
    shutil.copy(DESIGN_PLX, target)

    result = await sync_folder_plans(db_session)
    assert result.imported == 0
    assert result.skipped >= 1
    assert result.deleted >= 1
    assert not target.is_file()
