"""Хранение исходных DOCX для инкрементального экспорта «в оригинал»."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = os.getenv("UPLOADS_DIR", str(_PROJECT_ROOT / "uploads"))


def _uploads_root() -> Path:
    path = Path(UPLOADS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_source_path(document_id: uuid.UUID | str) -> Path:
    return _uploads_root() / f"{document_id}.docx"


def save_document_source(document_id: uuid.UUID, file_bytes: bytes) -> str:
    path = default_source_path(document_id)
    path.write_bytes(file_bytes)
    return str(path)


def copy_document_source(from_id: uuid.UUID, to_id: uuid.UUID) -> str | None:
    src = default_source_path(from_id)
    if not src.is_file():
        return None
    dest = default_source_path(to_id)
    shutil.copy2(src, dest)
    return str(dest)


def resolve_document_source_path(
    document_id: uuid.UUID | str,
    *,
    source_path: str | None = None,
) -> Path | None:
    if source_path:
        stored = Path(source_path)
        if stored.is_file():
            return stored
    fallback = default_source_path(document_id)
    if fallback.is_file():
        return fallback
    return None
