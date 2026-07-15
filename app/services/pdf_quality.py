"""Оценка качества текстового слоя PDF (legacy-документы ТЗ п. 1.4)."""

from __future__ import annotations

import re

_SPACED_LETTER_RE = re.compile(r"(?<=\s)[А-ЯA-Z](?:\s[А-ЯA-Z]){3,}(?=\s|$)")
_DISCIPLINE_CODE_RE = re.compile(
    r"(?:Б\d+(?:\.[А-ЯA-Z]+(?:\.\d+)*(?:\([А-ЯA-Z]+\))?)+|ФТД\.\d+)",
    re.IGNORECASE,
)
_CREDITS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*з\.?\s*е", re.IGNORECASE)


def assess_pdf_text_quality(text: str) -> dict[str, object]:
    """Возвращает quality: good|poor|empty и флаг ручного паспорта."""
    normalized = (text or "").strip()
    if not normalized:
        return {
            "quality": "empty",
            "needs_manual_passport": True,
            "score": 0.0,
            "reason": "empty_text_layer",
        }

    words = normalized.split()
    single_char_words = sum(1 for word in words if len(word) == 1 and word.isalpha())
    spaced_runs = len(_SPACED_LETTER_RE.findall(normalized))
    ratio = (single_char_words + spaced_runs * 3) / max(len(words), 1)

    has_code = bool(_DISCIPLINE_CODE_RE.search(normalized))
    has_credits = bool(_CREDITS_RE.search(normalized))
    passport_ok = has_code and has_credits

    if ratio >= 0.12 or spaced_runs >= 2:
        return {
            "quality": "poor",
            "needs_manual_passport": not passport_ok,
            "score": round(max(0.0, 1.0 - ratio), 3),
            "reason": "spaced_letters_or_fragmented_text",
            "passport_detected": passport_ok,
        }

    if not passport_ok:
        return {
            "quality": "partial",
            "needs_manual_passport": True,
            "score": 0.5,
            "reason": "passport_fields_missing",
            "passport_detected": False,
        }

    return {
        "quality": "good",
        "needs_manual_passport": False,
        "score": 1.0,
        "reason": "ok",
        "passport_detected": True,
    }
