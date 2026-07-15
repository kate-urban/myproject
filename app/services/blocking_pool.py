"""Ограниченный пул для блокирующих операций (LibreOffice, Word, PyMuPDF)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from app.config import blocking_io_max_parallel

T = TypeVar("T")

_sem: asyncio.Semaphore | None = None


def _get_sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(blocking_io_max_parallel())
    return _sem


async def run_blocking(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Выполнить sync-функцию в thread pool с ограничением параллелизма."""
    async with _get_sem():
        return await asyncio.to_thread(func, *args, **kwargs)
