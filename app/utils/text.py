"""Преобразование HTML разделов в plain text."""

from __future__ import annotations

from bs4 import BeautifulSoup

DEFAULT_PLAIN_TEXT_LIMIT = 1000


def html_to_plain_text(
    html: str,
    *,
    limit: int | None = None,
    separator: str = " ",
) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(separator=separator)
    if limit is not None and limit >= 0:
        return text[:limit]
    return text


def section_plain_text(html: str, limit: int = DEFAULT_PLAIN_TEXT_LIMIT) -> str:
    """Краткий plain text для поиска (с ограничением длины)."""
    return html_to_plain_text(html, limit=limit)
