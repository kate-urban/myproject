"""Приватное хранение PNG-подписей (не отдаются через /static)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tz import RefSignature

PRIVATE_PREFIX = "private/signatures/"
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def signatures_dir() -> Path:
    env = os.getenv("SIGNATURES_DIR", "").strip()
    if env:
        path = Path(env)
        if not path.is_absolute():
            path = project_root() / path
    else:
        path = project_root() / "data" / "private" / "signatures"
    path.mkdir(parents=True, exist_ok=True)
    return path


def signature_storage_key(filename: str) -> str:
    return f"{PRIVATE_PREFIX}{Path(filename).name}"


def store_signature_file(row_id, content: bytes, suffix: str) -> str:
    normalized = suffix.lower() if suffix else ".png"
    if normalized not in ALLOWED_SUFFIXES:
        normalized = ".png"
    target = signatures_dir() / f"{row_id}{normalized}"
    target.write_bytes(content)
    return signature_storage_key(target.name)


def resolve_signature_path(png_path: str | None, root: Path | None = None) -> Path | None:
    if not png_path:
        return None
    root = root or project_root()
    normalized = png_path.replace("\\", "/")

    direct = Path(png_path)
    if direct.is_file():
        return direct

    name = Path(normalized).name
    private = signatures_dir() / name
    if private.is_file():
        return private

    legacy = root / "static" / "signatures" / name
    if legacy.is_file():
        return legacy

    relative = root / normalized.lstrip("/")
    return relative if relative.is_file() else None


async def migrate_legacy_signatures(db: AsyncSession) -> None:
    """Переносит файлы из static/signatures в приватный каталог и обновляет пути в БД."""
    legacy_dir = project_root() / "static" / "signatures"
    if not legacy_dir.is_dir():
        return

    dest = signatures_dir()
    result = await db.execute(select(RefSignature).where(RefSignature.png_path.isnot(None)))
    changed = False
    for row in result.scalars():
        if not row.png_path or row.png_path.startswith(PRIVATE_PREFIX):
            continue
        name = Path(row.png_path).name
        src = legacy_dir / name
        if not src.is_file():
            continue
        dst = dest / name
        if not dst.is_file():
            shutil.copy2(src, dst)
        row.png_path = signature_storage_key(name)
        changed = True

    if changed:
        await db.flush()
