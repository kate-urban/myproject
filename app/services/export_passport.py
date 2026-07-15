"""Заполнение титульного листа макета РПД данными из УП и extract."""

from __future__ import annotations

import re

from docx import Document
from docx.table import Table

from app.services.rpd_extractor import RpdExtract

_ASSESSMENT_LABELS = {
    "exam": "экзамен",
    "zachet": "зачёт",
    "zachet_graded": "зачёт с оценкой",
    "kp": "курсовой проект",
    "kr": "курсовая работа",
    "control_work": "контрольная работа",
}


def _table_text(table: Table) -> str:
    return " ".join(cell.text.lower() for row in table.rows for cell in row.cells)


def _set_cell(table: Table, row: int, col: int, value: str) -> None:
    if not value or row >= len(table.rows):
        return
    cells = table.rows[row].cells
    if col >= len(cells):
        return
    cells[col].text = value.strip()


def _find_table(doc: Document, *markers: str) -> Table | None:
    for table in doc.tables:
        sample = _table_text(table)
        if all(marker in sample for marker in markers):
            return table
    return None


def _format_discipline_line(code: str | None, name: str | None) -> str:
    code = (code or "").strip()
    name = (name or "").strip()
    if code and name:
        return f"{code} {name}"
    return code or name


def _format_direction_line(code: str | None, name: str | None) -> str:
    code = (code or "").strip()
    name = (name or "").strip()
    if code and name:
        return f"{code} {name}"
    return code or name


def _control_label_from_assessments(assessments) -> str:
    if not assessments:
        return ""
    parts: list[str] = []
    seen: set[str] = set()
    for item in assessments:
        label = _ASSESSMENT_LABELS.get(getattr(item, "form_type", "") or "", "")
        if not label or label in seen:
            continue
        seen.add(label)
        parts.append(label)
    return ", ".join(parts)


def _fill_authors_table(table: Table, authors: list[str]) -> int:
    """Таблица «Составители» — до 3 авторов в последней колонке."""
    if not authors:
        return 0
    filled = 0
    author_rows = [1, 3, 5]
    for index, row_idx in enumerate(author_rows):
        if index >= len(authors):
            break
        if row_idx >= len(table.rows):
            break
        cells = table.rows[row_idx].cells
        if len(cells) >= 6:
            cells[5].text = authors[index]
            filled += 1
    return filled


def fill_passport_tables(
    doc: Document,
    *,
    rpd: RpdExtract | None = None,
    discipline_code: str | None = None,
    discipline_name: str | None = None,
    direction_code: str | None = None,
    direction_name: str | None = None,
    profile_name: str | None = None,
    department_name: str | None = None,
    credits: float | None = None,
    control_label: str | None = None,
    authors: list[str] | None = None,
) -> dict[str, int]:
    if rpd:
        discipline_code = discipline_code or rpd.discipline_code
        discipline_name = discipline_name or rpd.discipline_name
        direction_code = direction_code or rpd.direction_code
        profile_name = profile_name or rpd.profile_name
        credits = credits if credits is not None else rpd.credits
        authors = authors if authors is not None else list(rpd.authors or [])

    stats = {
        "discipline": 0,
        "direction": 0,
        "profile": 0,
        "department": 0,
        "credits": 0,
        "control": 0,
        "authors": 0,
    }

    discipline_line = _format_discipline_line(discipline_code, discipline_name)
    if discipline_line:
        table = _find_table(doc, "дисциплин")
        if table and len(table.rows) >= 2:
            target = table.rows[0].cells[1] if len(table.rows[0].cells) > 1 else table.rows[1].cells[0]
            target.text = discipline_line
            stats["discipline"] = 1

    direction_line = _format_direction_line(direction_code, direction_name)
    if direction_line:
        table = _find_table(doc, "направлен", "подготов")
        if table and len(table.rows) >= 2:
            target = table.rows[0].cells[1] if len(table.rows[0].cells) > 1 else table.rows[1].cells[0]
            target.text = direction_line
            stats["direction"] = 1

    if profile_name:
        table = _find_table(doc, "направленность", "профиль")
        if table and table.rows:
            cells = table.rows[0].cells
            if len(cells) > 1:
                cells[1].text = profile_name
                stats["profile"] = 1

    if department_name:
        table = _find_table(doc, "кафедра")
        if table and len(table.rows) >= 2 and "составител" not in _table_text(table):
            target = table.rows[0].cells[1] if len(table.rows[0].cells) > 1 else table.rows[1].cells[0]
            target.text = department_name
            stats["department"] = 1

    if credits is not None:
        table = _find_table(doc, "объем", "дисциплин")
        if table and table.rows:
            cells = table.rows[0].cells
            value = str(credits).replace(".", ",")
            for col in (2, 1):
                if col < len(cells):
                    if cells[col].text.strip() in ("", "–", "-"):
                        cells[col].text = value
                        stats["credits"] = 1
                        break

    if control_label:
        table = _find_table(doc, "форма контроля")
        if table and len(table.rows) >= 1:
            cells = table.rows[-1].cells if len(table.rows) > 1 else table.rows[0].cells
            for col in (2, 1):
                if col < len(cells):
                    cells[col].text = control_label
                    stats["control"] = 1
                    break

    authors_table = _find_table(doc, "ученое звание", "ф.и.о")
    if authors_table:
        stats["authors"] = _fill_authors_table(authors_table, authors or [])

    # Плейсхолдеры в абзацах титула (цель/задачи если остались пустые линии)
    if discipline_name:
        for paragraph in doc.paragraphs[:80]:
            text = paragraph.text
            if "«________________________________" in text:
                paragraph.text = re.sub(
                    r"«_{10,}»",
                    f"«{discipline_name}»",
                    text,
                    count=1,
                )
                break

    return stats
