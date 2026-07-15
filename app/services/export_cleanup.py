"""Удаление устаревших файлов из каталога экспорта."""

from __future__ import annotations

import time
from pathlib import Path

from app.config import export_retention_hours


def cleanup_exports_directory(
    exports_dir: str | Path,
    *,
    max_age_hours: int | None = None,
) -> dict[str, int]:
    """Удалить файлы старше max_age_hours. Возвращает removed и freed_bytes."""
    root = Path(exports_dir)
    if not root.is_dir():
        return {"removed": 0, "freed_bytes": 0}

    max_age = max_age_hours if max_age_hours is not None else export_retention_hours()
    cutoff = time.time() - max_age * 3600
    removed = 0
    freed = 0

    for path in root.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                size = path.stat().st_size
                path.unlink()
                removed += 1
                freed += size
        except OSError:
            continue

    return {"removed": removed, "freed_bytes": freed}
