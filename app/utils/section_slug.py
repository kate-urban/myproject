"""Slug для тегов {{SECTION_*}} в макетах."""

from __future__ import annotations

import re


def section_slug(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned[:80] or "section"
