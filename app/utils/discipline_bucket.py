"""Классификация дисциплин УП: дисциплины / практики / ГИА."""

from __future__ import annotations

import re

_GIA_RE = re.compile(r"(гиа|вкр|гос\.?\s*экз|итогов)", re.IGNORECASE)


def classify_discipline_bucket(
    *,
    code: str,
    name: str,
    object_type: str | None = None,
) -> str:
    code_upper = code.upper()
    name_upper = name.upper()
    if object_type == "3" or "(П)" in code_upper or code_upper.startswith("Б2"):
        return "practices"
    if code_upper.startswith("Б3") or _GIA_RE.search(name_upper):
        return "gia"
    return "disciplines"
