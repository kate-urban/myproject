"""Импорт кафедр из Excel (свод УП, отчёт 7.2 и т.п.)."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tz import RefDepartment

# Заголовки колонок (нижний регистр) → поле
_CODE_HEADERS = {
    "код кафедры",
    "шифр кафедры",
    "номер",
    "№",
}
_NAME_HEADERS = {
    "название кафедры",
    "наименование кафедры",
    "название",
}


@dataclass(frozen=True)
class DepartmentRow:
    code: str
    name: str
    source_sheet: str


def _norm_header(value) -> str:
    return str(value or "").strip().lower()


def _norm_code(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _norm_name(value) -> str:
    return str(value or "").strip()


def _find_columns(headers: list[str]) -> tuple[int | None, int | None]:
    code_idx = name_idx = None
    for idx, header in enumerate(headers):
        if header in _CODE_HEADERS and code_idx is None:
            code_idx = idx
        if header in _NAME_HEADERS and name_idx is None:
            name_idx = idx
    return code_idx, name_idx


def _parse_sheet(ws, sheet_name: str) -> list[DepartmentRow]:
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return []

    headers = [_norm_header(cell) for cell in header_row]
    code_idx, name_idx = _find_columns(headers)
    if code_idx is None or name_idx is None:
        return []

    out: list[DepartmentRow] = []
    for row in rows_iter:
        if not row or all(cell is None for cell in row):
            continue
        code = _norm_code(row[code_idx] if code_idx < len(row) else None)
        name = _norm_name(row[name_idx] if name_idx < len(row) else None)
        if not code or not name:
            continue
        out.append(DepartmentRow(code=code, name=name, source_sheet=sheet_name))
    return out


def parse_departments_workbook(wb) -> tuple[list[DepartmentRow], list[str]]:
    warnings: list[str] = []
    collected: list[DepartmentRow] = []

    for sheet_name in wb.sheetnames:
        parsed = _parse_sheet(wb[sheet_name], sheet_name)
        if parsed:
            collected.extend(parsed)
        else:
            headers = []
            ws = wb[sheet_name]
            try:
                header_row = next(ws.iter_rows(values_only=True))
                headers = [_norm_header(c) for c in header_row]
            except StopIteration:
                pass
            if any(h in _CODE_HEADERS for h in headers) and not any(h in _NAME_HEADERS for h in headers):
                warnings.append(
                    f"Лист «{sheet_name}»: есть код кафедры, но нет названия — "
                    f"нужен файл с колонкой «Название кафедры» (свод УП FGOS3, отчёт 7.2 «Справочник»)."
                )

    unique: dict[tuple[str, str], DepartmentRow] = {}
    for row in collected:
        unique[(row.code, row.name)] = row

    if not unique and not warnings:
        warnings.append(
            "Не найдено строк с колонками «Код/Шифр кафедры» и «Название кафедры». "
            "Подходят: свод УП FGOS3, лист «Справочник» отчёта 7.2."
        )

    return list(unique.values()), warnings


def parse_departments_from_stream(source: BinaryIO) -> tuple[list[DepartmentRow], list[str]]:
    wb = load_workbook(source, read_only=True, data_only=True)
    try:
        return parse_departments_workbook(wb)
    finally:
        wb.close()


def parse_departments_from_bytes(content: bytes) -> tuple[list[DepartmentRow], list[str]]:
    return parse_departments_from_stream(BytesIO(content))


def parse_departments_from_xlsx(path: Path) -> tuple[list[DepartmentRow], list[str]]:
    """Возвращает уникальные пары (код, название) и предупреждения."""
    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return parse_departments_workbook(wb)
    finally:
        wb.close()


async def persist_department_rows(
    db: AsyncSession,
    rows: list[DepartmentRow],
) -> dict[str, int]:
    added = skipped = 0
    for row in sorted(rows, key=lambda r: (r.code, r.name)):
        exists = await db.execute(
            select(RefDepartment.id).where(
                RefDepartment.code == row.code,
                RefDepartment.name == row.name,
            )
        )
        if exists.scalar_one_or_none():
            skipped += 1
            continue
        db.add(RefDepartment(code=row.code, name=row.name))
        added += 1
    if added:
        await db.flush()
    await db.commit()
    return {"added": added, "skipped": skipped, "total": len(rows)}
