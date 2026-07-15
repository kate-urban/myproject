"""Тесты пула блокирующих операций."""

from __future__ import annotations

import time

import pytest

from app.services import blocking_pool


@pytest.mark.asyncio
async def test_run_blocking_executes_function() -> None:
    result = await blocking_pool.run_blocking(lambda x: x + 1, 41)
    assert result == 42


@pytest.mark.asyncio
async def test_run_blocking_serializes_with_limit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BLOCKING_IO_MAX_PARALLEL", "1")
    blocking_pool._sem = None

    peaks: list[int] = []
    active = 0

    def job() -> None:
        nonlocal active
        active += 1
        peaks.append(active)
        time.sleep(0.03)
        active -= 1

    await blocking_pool.run_blocking(job)
    await blocking_pool.run_blocking(job)
    assert max(peaks) == 1
