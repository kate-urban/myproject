"""Тесты очистки каталога экспорта."""

from __future__ import annotations

import time
from pathlib import Path

from app.services.export_cleanup import cleanup_exports_directory


def test_cleanup_removes_old_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORT_RETENTION_HOURS", "24")
    old = tmp_path / "old.docx"
    fresh = tmp_path / "fresh.docx"
    old.write_bytes(b"x" * 100)
    fresh.write_bytes(b"y" * 50)

    old_time = time.time() - 48 * 3600
    Path(old).touch()
    import os

    os.utime(old, (old_time, old_time))

    result = cleanup_exports_directory(tmp_path)
    assert result["removed"] == 1
    assert result["freed_bytes"] == 100
    assert not old.exists()
    assert fresh.exists()


def test_cleanup_empty_dir(tmp_path: Path) -> None:
    assert cleanup_exports_directory(tmp_path) == {"removed": 0, "freed_bytes": 0}


def test_cleanup_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert cleanup_exports_directory(missing) == {"removed": 0, "freed_bytes": 0}
