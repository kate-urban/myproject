"""Импорт учебного плана из Excel *_plx.xlsx (экспорт UpVo / MMIS)."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import openpyxl

from app.services.importers.dto import AssessmentDTO, DisciplineDTO, StudyPlanDTO
from app.utils.plan_title import (
    PlanTitleInfo,
    form_from_filename,
    parse_titul,
    year_from_filename,
)

# Б1.О.01, Б2.О.03(П), ФТД.01 …
DISCIPLINE_CODE_RE = re.compile(r"^(?:Б\d[\w.()]*|ФТД\.\d+)$", re.IGNORECASE)

# Фиксированные колонки листа «План» (строка заголовков — «Индекс» в col B).
COL_IN_PLAN = 1
COL_CODE = 2
COL_NAME = 3
COL_CREDITS_FACT = 10
COL_HOURS_TOTAL = 12
COL_HOURS_CONTACT = 13
COL_HOURS_SR = 14
COL_HOURS_CONTROL = 15

COMP_COL_INDEX_END = 4
COMP_COL_NAME = 5
COMP_COL_LIST = 6


def _cell_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _cell_float(value: object) -> float | None:
    text = _cell_str(value).replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cell_int(value: object) -> int | None:
    number = _cell_float(value)
    if number is None:
        return None
    return int(number)


def _parse_competency_list(raw: object) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in str(raw).split(";") if part.strip()]


def _leaf_discipline_code(cells: list[object]) -> str | None:
    for value in reversed(cells[:COMP_COL_INDEX_END]):
        code = _cell_str(value)
        if code and DISCIPLINE_CODE_RE.match(code):
            return code
    return None


def _competencies_for_code(code: str, comp_map: dict[str, list[str]]) -> list[str]:
    if code in comp_map:
        return comp_map[code]

    best: list[str] | None = None
    best_len = -1
    for key, items in comp_map.items():
        if code == key or code.startswith(f"{key}."):
            if len(key) > best_len:
                best_len = len(key)
                best = items
    return best or []


def _find_header_row(ws: openpyxl.worksheet.worksheet.Worksheet) -> int:
    for row_idx, row in enumerate(
        ws.iter_rows(min_row=1, max_row=10, values_only=True), start=1
    ):
        if not row or len(row) < COL_CODE:
            continue
        label = _cell_str(row[COL_CODE - 1])
        if "индекс" in label.lower():
            return row_idx
    return 3


def _row_value(row: tuple[object, ...] | list[object], col: int) -> object:
    if len(row) < col:
        return None
    return row[col - 1]


def _split_hour_columns(row: tuple[object, ...] | list[object]) -> tuple[int | None, int | None, int | None, int | None]:
    """M=контакт, N=СР или ауд., O=контроль (если O пуст — N это ауд.)."""
    contact = _cell_int(_row_value(row, COL_HOURS_CONTACT))
    middle = _cell_int(_row_value(row, COL_HOURS_SR))
    control = _cell_int(_row_value(row, COL_HOURS_CONTROL))
    if control is not None:
        return contact, None, middle, control
    return contact, middle, None, None


def _read_titul(wb: openpyxl.Workbook, filename: str) -> PlanTitleInfo:
    if "Титул" in wb.sheetnames:
        ws = wb["Титул"]
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                text = _cell_str(cell)
                if not text:
                    continue
                info = parse_titul(text)
                if info:
                    return info
                direction_match = re.search(
                    r"(\d{2}\.\d{2}\.\d{2})", text
                )
                if direction_match and "направлен" in text.lower():
                    return PlanTitleInfo(
                        direction_code=direction_match.group(1),
                        direction_name=text,
                        profile_name=text,
                    )

    raise ValueError(
        f"Не удалось прочитать направление/профиль из листа «Титул» в {filename}"
    )


def _read_competencies(wb: openpyxl.Workbook) -> dict[str, list[str]]:
    sheet_name = next(
        (name for name in wb.sheetnames if name.startswith("Компетенции(2)")),
        None,
    )
    if sheet_name is None:
        return {}

    ws = wb[sheet_name]
    comp_map: dict[str, list[str]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        code = _leaf_discipline_code(list(row))
        if not code:
            continue
        competencies = _parse_competency_list(
            row[COMP_COL_LIST - 1] if len(row) >= COMP_COL_LIST else None
        )
        if competencies:
            comp_map[code] = competencies
    return comp_map


def _parse_assessment_columns(
    ws: openpyxl.worksheet.worksheet.Worksheet, header_row: int
) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for row_idx in range(max(1, header_row - 1), header_row + 2):
        rows = list(
            ws.iter_rows(min_row=row_idx, max_row=row_idx, values_only=True)
        )
        if not rows:
            continue
        for idx, cell in enumerate(rows[0]):
            label = _cell_str(cell).lower()
            if not label:
                continue
            if "экзам" in label:
                mapping.setdefault("exam", idx)
            elif "зач" in label and "оцен" in label:
                mapping.setdefault("zachet_graded", idx)
            elif "зач" in label:
                mapping.setdefault("zachet", idx)
            elif "курсов" in label and "проект" in label:
                mapping.setdefault("kp", idx)
            elif "курсов" in label and "работ" in label:
                mapping.setdefault("kr", idx)
    return mapping


def _assessments_from_row(
    row: tuple[object, ...] | list[object], col_map: dict[str, int]
) -> list[AssessmentDTO]:
    items: list[AssessmentDTO] = []
    for form_type, col_idx in col_map.items():
        if col_idx >= len(row):
            continue
        raw = row[col_idx]
        text = _cell_str(raw)
        if not text or text in {"-", "–", "—", "0"}:
            continue
        semester = _cell_int(raw)
        if semester is None and text in {"+", "++", "v", "V", "да"}:
            items.append(AssessmentDTO(form_type=form_type))
        elif semester is not None:
            items.append(AssessmentDTO(form_type=form_type, semester=semester))
        elif text:
            items.append(AssessmentDTO(form_type=form_type))
    return items


def _read_plan_disciplines(
    wb: openpyxl.Workbook, comp_map: dict[str, list[str]]
) -> list[DisciplineDTO]:
    if "План" not in wb.sheetnames:
        raise ValueError("Лист «План» не найден")

    ws = wb["План"]
    header_row = _find_header_row(ws)
    assessment_cols = _parse_assessment_columns(ws, header_row)
    disciplines: list[DisciplineDTO] = []

    for row_idx, row in enumerate(
        ws.iter_rows(min_row=header_row + 1, values_only=True),
        start=header_row + 1,
    ):
        if not row:
            continue

        code = _cell_str(_row_value(row, COL_CODE))
        name = _cell_str(_row_value(row, COL_NAME))
        if not code or not DISCIPLINE_CODE_RE.match(code):
            continue
        if not name:
            continue

        in_plan_raw = _cell_str(_row_value(row, COL_IN_PLAN))
        in_plan = in_plan_raw == "+"
        hours_contact, hours_aud, hours_sr, hours_control = _split_hour_columns(row)

        disciplines.append(
            DisciplineDTO(
                code=code,
                name=name,
                in_plan=in_plan,
                credits=_cell_float(_row_value(row, COL_CREDITS_FACT)),
                hours_total=_cell_int(_row_value(row, COL_HOURS_TOTAL)),
                hours_contact=hours_contact,
                hours_aud=hours_aud,
                hours_sr=hours_sr,
                hours_control=hours_control,
                row_order=row_idx,
                competencies=sorted(set(_competencies_for_code(code, comp_map))),
                assessments=_assessments_from_row(row, assessment_cols),
            )
        )

    return disciplines


class PlxExcelReader:
    """Читает *_plx.xlsx и возвращает StudyPlanDTO."""

    def read(self, path: str | Path) -> StudyPlanDTO:
        file_path = Path(path)
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            return self._read_workbook(wb, file_path.name)
        finally:
            wb.close()

    def read_bytes(self, content: bytes, filename: str) -> StudyPlanDTO:
        wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            return self._read_workbook(wb, filename)
        finally:
            wb.close()

    def _read_workbook(
        self, wb: openpyxl.Workbook, filename: str
    ) -> StudyPlanDTO:
        title_info = _read_titul(wb, filename)
        comp_map = _read_competencies(wb)
        disciplines = _read_plan_disciplines(wb, comp_map)

        return StudyPlanDTO(
            source_file=filename,
            source_format="plx_excel",
            direction_code=title_info.direction_code,
            direction_name=title_info.direction_name,
            profile_name=title_info.profile_name,
            form=form_from_filename(filename),
            year=year_from_filename(filename),
            disciplines=disciplines,
        )
