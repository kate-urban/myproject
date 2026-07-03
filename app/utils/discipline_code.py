"""Нормализация шифров дисциплин: DOCX-паспорт, имя файла ↔ код УП."""

from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document

DISCIPLINE_CODE_RE = re.compile(
    r"(?:Б\d+(?:\.[А-ЯA-Z]+(?:\.\d+)*(?:\([А-ЯA-Z]+\))?)+|ФТД\.\d+)",
    re.IGNORECASE,
)

# Версия парсера шифров (для проверки после обновления: /api/v1/system/info).
PARSER_VERSION = "2026-07-02-dv"
_INCOMPLETE_CODE_RE = re.compile(r"^Б\d+\.[ОВ]$", re.IGNORECASE)


def _segment_to_cyrillic(segment: str) -> str:
    upper = segment.upper()
    if upper == "O":
        return "О"
    if upper == "V":
        return "В"
    if upper == "DV":
        return "ДВ"
    if upper.startswith("B") and segment[1:].isdigit():
        return "Б" + segment[1:]
    return segment


def _is_incomplete_code(code: str | None) -> bool:
    if not code:
        return True
    return bool(_INCOMPLETE_CODE_RE.match(code.strip()))


def _pick_best_code(*codes: str | None) -> str | None:
    candidates = [code.strip() for code in codes if code and code.strip()]
    if not candidates:
        return None
    complete = [code for code in candidates if not _is_incomplete_code(code)]
    pool = complete or candidates
    return max(pool, key=lambda code: (code.count("."), len(code)))


def _codes_in_text(text: str) -> list[str]:
    return [match.group(0) for match in DISCIPLINE_CODE_RE.finditer(text)]


def code_from_filename(filename: str) -> str | None:
    parts = Path(filename).stem.split("_")
    if not parts:
        return None

    if parts[0].upper() == "FOS":
        parts = parts[1:]
    if not parts:
        return None

    if parts[0].upper() == "FTD" and len(parts) > 1 and parts[1].isdigit():
        return f"ФТД.{parts[1]}"

    code_parts: list[str] = []
    for part in parts:
        upper = part.upper()
        if re.fullmatch(r"K\d+", upper):
            break
        if upper == "P":
            if code_parts:
                code_parts[-1] += "(П)"
            continue
        if upper in ("O", "V", "DV") or re.fullmatch(r"B\d+", upper) or part.isdigit():
            code_parts.append(_segment_to_cyrillic(part))
            continue
        break

    return ".".join(code_parts) if code_parts else None


def extract_passport_from_docx(file_bytes: bytes) -> dict[str, str]:
    doc = Document(io.BytesIO(file_bytes))
    result: dict[str, str] = {}
    discipline_codes: list[str] = []

    for table in doc.tables[:8]:
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            value = cells[-1] if len(cells) == 2 else " | ".join(cells[1:])
            if "объем" in label or "объём" in label:
                continue
            if "дисциплин" in label or "практик" in label:
                row_text = " ".join(cells[1:])
                discipline_codes.extend(_codes_in_text(row_text))
                discipline_codes.extend(_codes_in_text(value))
                if not result.get("discipline_raw"):
                    result["discipline_raw"] = value
            elif "направлен" in label and "профил" not in label:
                result["direction_raw"] = value
            elif "профиль" in label or "направленност" in label:
                result["profile_name"] = value

    if discipline_codes:
        result["discipline_code"] = max(discipline_codes, key=len)
    return result


def resolve_discipline_code(file_bytes: bytes, filename: str) -> str | None:
    passport = extract_passport_from_docx(file_bytes)
    passport_code = passport.get("discipline_code")
    filename_code = code_from_filename(filename)

    if filename_code and not _is_incomplete_code(filename_code):
        if _is_incomplete_code(passport_code):
            return filename_code
        return _pick_best_code(filename_code, passport_code)

    if passport_code and not _is_incomplete_code(passport_code):
        return passport_code

    return _pick_best_code(filename_code, passport_code)


def normalize_discipline_code(code: str | None) -> str:
    return (code or "").strip().upper()
