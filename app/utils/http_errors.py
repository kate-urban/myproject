"""Безопасные сообщения об ошибках для API (без утечки внутренних деталей)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def public_error_message(
    exc: BaseException,
    *,
    fallback: str = "Внутренняя ошибка сервера",
    log: bool = True,
) -> str:
    if log:
        logger.exception("API error: %s", exc)
    return fallback
