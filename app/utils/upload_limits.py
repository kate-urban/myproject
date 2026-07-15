"""Ограничение размера загружаемых файлов."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from app.config import max_upload_bytes

_CHUNK = 1024 * 1024


async def read_upload_bytes(upload: UploadFile, *, max_bytes: int | None = None) -> bytes:
    """Читает UploadFile с лимитом; не загружает весь файл в память одним блоком."""
    limit = max_bytes if max_bytes is not None else max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            mb = limit // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой (лимит {mb} МБ)",
            )
        chunks.append(chunk)
    return b"".join(chunks)
