"""Дополнительное извлечение полей РПД по ТЗ (разделы 2.1, 3.1, 3.5, 3.6)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from docx import Document

from app.services.rpd_extractor import (
    COMPETENCY_CODE_RE,
    INDICATOR_CODE_RE,
    _classify_table,
    _first_form_hours,
    _has_topic_marker,
    _parse_int_cell,
)

ZUV_MARKER_RE = re.compile(r"(знать|уметь|владеть)\s*[:\n]", re.IGNORECASE)
ZUV_MARKER_LOOSE_RE = re.compile(r"(?:^|[\n;\s])(знать|уметь|владеть)\b", re.IGNORECASE)
QUESTION_NUM_RE = re.compile(r"^(\d+)\.(\d+)\.?\s*")
TOPIC_NUM_RE = re.compile(r"^(\d+)\.?\s*")
PLUS_MINUS_RE = re.compile(r"^[+\−\-–—]|^(?:есть|нет|да|нет\b)", re.IGNORECASE)


@dataclass
class TzExtract:
    """Поля для правил R015–R019 / R024–R027 (additive к RpdExtract)."""

    section2_zuv_by_indicator: dict[str, list[str]] = field(default_factory=dict)
    topics31_zuv_phrases: list[str] = field(default_factory=list)
    topics31_flag_hour_violations: list[str] = field(default_factory=list)
    topics31_has_flag_columns: bool = False
    topics31_assessments: list[dict] = field(default_factory=list)
    topic_titles_bold: list[dict] = field(default_factory=list)
    topic_numbers: list[int] = field(default_factory=list)
    topic_names: dict[int, str] = field(default_factory=dict)
    sr_rows: list[dict] = field(default_factory=list)
    sr_has_current_control: bool = False
    sr_has_homework_control: bool = False
    sr_table_total_from_rows: int | None = None
    sr_control_work_hours: int | None = None
    sr_course_work_hours_35: int | None = None
    sr_course_project_hours_35: int | None = None
    sr_questions: list[dict] = field(default_factory=list)
    sr_questions_hours_total: int | None = None
    sr_self_study_budget_hours: int | None = None
    matrix_36_rows: list[dict] = field(default_factory=list)
    matrix_36_col_totals: dict[str, int | None] = field(default_factory=dict)
    pk_indicators_without_group: list[str] = field(default_factory=list)
    pk_groups_ok: bool | None = None


def _normalize_phrase(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[\u2013\u2014\u2212\-–—]", "-", cleaned)
    cleaned = re.sub(r"[;:,.!?«»\"\"„\"()]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -")


def _has_zuv_markers(text: str) -> bool:
    return bool(ZUV_MARKER_LOOSE_RE.search(text))


def _split_zuv_phrases(text: str) -> list[str]:
    """Разбить текст З/У/В на отдельные формулировки."""
    if not text.strip():
        return []
    markers = list(
        re.finditer(r"(?im)(знать|уметь|владеть)\s*[:\n]?\s*", text)
    )
    if not markers:
        if _has_zuv_markers(text):
            return [_normalize_phrase(text)]
        return [_normalize_phrase(text)] if text.strip() else []

    parts: list[str] = []
    for idx, match in enumerate(markers):
        start = match.end()
        end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        chunk = text[start:end].strip(" ;,\n")
        if chunk:
            parts.append(_normalize_phrase(f"{match.group(1).lower()}: {chunk}"))
    return parts


def _indicator_codes_in_text(text: str) -> list[str]:
    return [m.group(0).upper() for m in INDICATOR_CODE_RE.finditer(text)]


def _row_relevant_for_discipline(row_text: str, discipline_name: str | None) -> bool:
    """Если в строке несколько дисциплин — оставить только релевантные."""
    if not discipline_name:
        return True
    lowered = row_text.lower()
    name = discipline_name.lower().strip()
    stem = name[: max(5, min(len(name), 8))]
    if name in lowered or stem in lowered:
        return True
    if ";" in row_text and any(
        marker in lowered for marker in ("других дисциплин", "иной дисциплин", "гидромелиора", "почвовед")
    ):
        return False
    return True


_ZUV_LEADING_CODES_RE = re.compile(
    r"^((?:ук|опк|пк|пск)[\s-]*\d+(?:\.\d+)?[\s:.,-]*)+",
    re.IGNORECASE,
)
_ZUV_TRAILING_CODES_RE = re.compile(
    r"(?:\s*(?:ук|опк|пк|пск)[\s-]*(?:\d+[\s.-]*)?[\d.]*)+$",
    re.IGNORECASE,
)


def _clean_zuv_phrase(text: str) -> str:
    cleaned = text.strip().lstrip("-: ")
    cleaned = _ZUV_LEADING_CODES_RE.sub("", cleaned)
    cleaned = re.sub(r"\b(?:ук|опк|пк|пск)[\s-]*\d+(?:\.\d+)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = _ZUV_TRAILING_CODES_RE.sub("", cleaned)
    return _normalize_phrase(cleaned)


def _competency_table_columns(table) -> tuple[int | None, int | None]:
    zuv_col: int | None = None
    indicator_col: int | None = None
    for row in table.rows[:2]:
        for idx, cell in enumerate(row.cells):
            label = cell.text.lower().replace("\n", " ")
            if "результат" in label and "обучен" in label:
                zuv_col = idx
            if "индикатор" in label:
                indicator_col = idx
    if zuv_col is None and table.rows and len(table.rows[0].cells) >= 3:
        zuv_col = len(table.rows[0].cells) - 1
    return zuv_col, indicator_col


def _extract_section2_zuv(doc: Document, discipline_name: str | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_table(header, second) != "competencies":
            continue
        zuv_col, indicator_col = _competency_table_columns(table)
        if zuv_col is None:
            continue
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            if zuv_col >= len(cells):
                continue
            zuv_text = cells[zuv_col]
            if not zuv_text or not _has_zuv_markers(zuv_text):
                continue
            if not _row_relevant_for_discipline(zuv_text, discipline_name):
                continue
            indicator_text = (
                cells[indicator_col]
                if indicator_col is not None and indicator_col < len(cells)
                else ""
            )
            codes = _indicator_codes_in_text(indicator_text) or _indicator_codes_in_text(zuv_text)
            phrases = [_clean_zuv_phrase(p) for p in _split_zuv_phrases(zuv_text)]
            phrases = [p for p in phrases if p]
            if not phrases:
                continue
            if codes:
                for code in codes:
                    bucket = result.setdefault(code, [])
                    for phrase in phrases:
                        if phrase not in bucket:
                            bucket.append(phrase)
            else:
                bucket = result.setdefault("_ungrouped", [])
                for phrase in phrases:
                    if phrase not in bucket:
                        bucket.append(phrase)
    return result


def _extract_topics31_zuv(doc: Document) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        kind = _classify_table(header, second)
        if kind not in {"topics_31", "topics_detail"}:
            continue
        zuv_col: int | None = None
        for row in table.rows[:3]:
            for idx, cell in enumerate(row.cells):
                label = cell.text.lower().replace("\n", " ")
                if "результат" in label or "знать" in label or "уметь" in label:
                    zuv_col = idx
                    break
        if zuv_col is None:
            for row in table.rows[1:]:
                row_text = " ".join(c.text.strip() for c in row.cells if c.text.strip())
                if _has_zuv_markers(row_text):
                    for phrase in _split_zuv_phrases(row_text):
                        cleaned = _clean_zuv_phrase(phrase)
                        if cleaned and cleaned not in seen:
                            seen.add(cleaned)
                            phrases.append(cleaned)
            continue
        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if zuv_col >= len(cells):
                continue
            cell_text = cells[zuv_col]
            if not _has_zuv_markers(cell_text):
                continue
            for phrase in _split_zuv_phrases(cell_text):
                cleaned = _clean_zuv_phrase(phrase)
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    phrases.append(cleaned)
    return phrases


def _flag_column_indices(table) -> dict[str, int]:
    flags: dict[str, int] = {}
    for row in table.rows[:3]:
        for idx, cell in enumerate(row.cells):
            label = cell.text.lower().replace("\n", " ").replace("-", "")
            if "курсов" in label and "проект" in label:
                flags["kp"] = idx
            elif "курсов" in label and "работ" in label:
                flags["kr"] = idx
            elif "контрольн" in label and "работ" in label:
                flags["kr_ctrl"] = idx
    return flags


def _is_flag_cell_valid(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned or cleaned in {"-", "–", "—", "0"}:
        return True
    if PLUS_MINUS_RE.match(cleaned):
        return True
    if _parse_int_cell(cleaned) is not None:
        return False
    return True


def _extract_topics31_flags(doc: Document) -> tuple[list[str], bool]:
    violations: list[str] = []
    scanned = False
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_table(header, second) != "topics_31":
            continue
        flag_cols = _flag_column_indices(table)
        if not flag_cols:
            continue
        scanned = True
        for row in table.rows[2:]:
            cells = [c.text.strip() for c in row.cells]
            if not cells:
                continue
            label = cells[0].lower()
            if "итого" in label or "всего" in label:
                continue
            topic_match = TOPIC_NUM_RE.match(cells[0])
            if not topic_match and not any(c.isdigit() for c in cells[0][:3]):
                continue
            for flag_name, col_idx in flag_cols.items():
                if col_idx >= len(cells):
                    continue
                cell = cells[col_idx]
                if cell and not _is_flag_cell_valid(cell):
                    violations.append(f"тема {cells[0]}: {flag_name}={cell!r}")
    return violations, scanned


def _extract_topic_summaries(doc: Document) -> tuple[list[int], dict[int, str]]:
    numbers: list[int] = []
    names: dict[int, str] = {}
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        kind = _classify_table(header, second)
        if kind not in {"topics_31", "topics_detail", "matrix_36"}:
            if _classify_matrix_table(header, second):
                kind = "matrix_36"
            elif _has_topic_marker(header) and "№" in header and "тем" in header:
                kind = "matrix_36"
            else:
                continue
        if kind == "topics_31" and "темы (разделы)" not in header and "темы(разделы)" not in header:
            if not _classify_matrix_table(header, second):
                continue
        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 2:
                continue
            num_match = TOPIC_NUM_RE.match(cells[0])
            if not num_match:
                continue
            num = int(num_match.group(1))
            if num in names:
                continue
            name = cells[1] if len(cells) > 1 else ""
            if name and "итого" not in name.lower():
                numbers.append(num)
                names[num] = name[:120]
    return sorted(set(numbers)), names


def _classify_matrix_table(header: str, second: str) -> bool:
    full = re.sub(r"\s+", " ", f"{header} {second}".lower())
    has_topic = bool(
        re.search(r"№\s*тем", full)
        or "наименование темы" in full
        or ("№" in full and "тем" in full and "дисциплин" in full)
    )
    has_volume = any(
        token in full
        for token in (
            "объем работы",
            "объём работы",
            "объем ра",
            "объём ра",
            "лекции",
            "лек ",
        )
    )
    return has_topic and has_volume


def _matrix_column_indices(table) -> dict[str, int | None]:
    cols: dict[str, int | None] = {
        "lec": None,
        "prac": None,
        "lab": None,
        "sr": None,
        "total": None,
    }
    for row in table.rows[:3]:
        for idx, cell in enumerate(row.cells):
            label = cell.text.lower().replace("\n", " ").replace("-", "")
            if cols["lec"] is None and "лек" in label:
                cols["lec"] = idx
            if cols["prac"] is None and ("практ" in label or "семинар" in label):
                cols["prac"] = idx
            if cols["lab"] is None and "лабор" in label:
                cols["lab"] = idx
            if cols["sr"] is None and "самостоят" in label:
                cols["sr"] = idx
            if cols["total"] is None and "всего" in label and "час" in label:
                cols["total"] = idx
    return cols


def _extract_matrix_36(doc: Document) -> tuple[list[dict], dict[str, int | None]]:
    rows: list[dict] = []
    col_totals: dict[str, int | None] = {}
    for table in doc.tables:
        if len(table.rows) < 3:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if not _classify_matrix_table(header, second):
            continue
        cols = _matrix_column_indices(table)
        table_rows: list[dict] = []
        for row in table.rows[2:]:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            if "итого" in label or "всего" in label:
                col_totals = {
                    key: _parse_int_cell(cells[idx]) if idx is not None and idx < len(cells) else None
                    for key, idx in cols.items()
                }
                continue
            num_match = TOPIC_NUM_RE.match(cells[0])
            if not num_match:
                continue
            topic_num = int(num_match.group(1))
            name = cells[1] if len(cells) > 1 else None
            entry = {
                "topic": topic_num,
                "name": name,
                "lec": _parse_int_cell(cells[cols["lec"]]) if cols["lec"] is not None else None,
                "prac": _parse_int_cell(cells[cols["prac"]]) if cols["prac"] is not None else None,
                "lab": _parse_int_cell(cells[cols["lab"]]) if cols["lab"] is not None else None,
                "sr": _parse_int_cell(cells[cols["sr"]]) if cols["sr"] is not None else None,
                "total": _parse_int_cell(cells[cols["total"]]) if cols["total"] is not None else None,
            }
            if entry["total"] is None:
                parts = [entry[k] for k in ("lec", "prac", "lab", "sr") if entry[k] is not None]
                if parts:
                    entry["total"] = sum(parts)
            table_rows.append(entry)
        if table_rows:
            rows = table_rows
    return rows, col_totals


def _ochnaya_hours_column(table) -> int:
    """Колонка часов очной формы в таблице 3.5 (не очно-заочной / заочной)."""
    for row in table.rows[:3]:
        for idx, cell in enumerate(row.cells):
            label = cell.text.lower().replace("\n", " ").replace("-", "")
            if "очнозаоч" in label or "заоч" in label:
                continue
            if "очная" in label or ("очн" in label and "форма" in label):
                return idx
    return 1


def _hours_from_row(cells: list[str], col_idx: int) -> int | None:
    if col_idx >= len(cells):
        return None
    parsed = _parse_int_cell(cells[col_idx])
    if parsed is not None:
        return parsed
    if cells[col_idx].strip() in {"", "-", "–", "—", "0"}:
        return None
    return _parse_int_cell(cells[col_idx])


def _extract_sr_rows_extended(doc: Document) -> tuple[list[dict], bool, bool, int | None, int | None, int | None, int | None]:
    sr_rows: list[dict] = []
    has_homework = False
    has_current = False
    control_hours: int | None = None
    kr_hours: int | None = None
    kp_hours: int | None = None
    table_total: int | None = None

    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_table(header, second) != "sr_35":
            continue

        ochnaya_col = _ochnaya_hours_column(table)
        for row in table.rows[2:]:
            cells = [cell.text.strip() for cell in row.cells]
            if not cells:
                continue
            label = cells[0].lower().replace("\n", " ")
            if "итого" in label and "ср" in label:
                table_total = _hours_from_row(cells, ochnaya_col)
                continue
            hours = _hours_from_row(cells, ochnaya_col)
            sr_rows.append({"label": cells[0].strip(), "hours": hours})

            if "текущ" in label and "контрол" in label:
                has_current = True
            if "домашн" in label and "контрольн" in label:
                has_homework = True
            if "контрольн" in label and "работ" in label and "домашн" not in label:
                control_hours = hours
            elif "курсов" in label and "работ" in label and "проект" not in label:
                kr_hours = hours
            elif "курсов" in label and "проект" in label:
                kp_hours = hours

        break

    return sr_rows, has_current, has_homework, control_hours, kr_hours, kp_hours, table_total


def _extract_sr_questions(doc: Document) -> tuple[list[dict], int | None]:
    questions: list[dict] = []
    total = 0
    for table in doc.tables:
        if len(table.rows) < 2:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        if "вопрос" not in header and "самостоятель" not in header:
            has_xy = False
            for row in table.rows[1:4]:
                cells = [c.text.strip() for c in row.cells]
                if cells and QUESTION_NUM_RE.match(cells[0]):
                    has_xy = True
                    break
            if not has_xy:
                continue

        hours_col = 1
        for row in table.rows[:2]:
            for idx, cell in enumerate(row.cells):
                if "час" in cell.text.lower() or "трудо" in cell.text.lower():
                    hours_col = idx
                    break

        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if not cells:
                continue
            match = QUESTION_NUM_RE.match(cells[0])
            if not match:
                continue
            topic_num = int(match.group(1))
            hours = _first_form_hours(cells) if len(cells) > 1 else _parse_int_cell(
                cells[hours_col] if hours_col < len(cells) else ""
            )
            if hours is None:
                hours = _parse_int_cell(cells[-1]) if len(cells) > 1 else None
            entry = {
                "number": f"{match.group(1)}.{match.group(2)}",
                "topic": topic_num,
                "hours": hours,
                "text": cells[1] if len(cells) > 1 else None,
            }
            questions.append(entry)
            if hours is not None:
                total += hours

    return questions, (total if questions else None)


def _extract_pk_groups(doc: Document) -> tuple[bool | None, list[str]]:
    """ПК должны иметь группы; УК/ОПК — опционально."""
    pk_without_group: list[str] = []
    current_group: str | None = None
    found_pk = False

    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_table(header, second) != "competencies":
            continue

        for row in table.rows[1:]:
            row_text = " ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if not row_text:
                continue
            lowered = row_text.lower()
            if "профессиональн" in lowered and "компетенц" in lowered and not INDICATOR_CODE_RE.search(row_text):
                current_group = row_text[:80]
                continue
            codes = _indicator_codes_in_text(row_text)
            for code in codes:
                if not code.startswith("ПК-"):
                    continue
                found_pk = True
                if not current_group:
                    pk_without_group.append(code)
        if found_pk:
            break

    if not found_pk:
        return None, []
    return len(pk_without_group) == 0, sorted(set(pk_without_group))


def _sr_self_study_budget(sr_rows: list[dict]) -> int | None:
    for row in sr_rows:
        label = row.get("label", "").lower()
        if "самостоятельн" in label and "изучен" in label:
            return row.get("hours")
    return None


def _parse_assessment_form_type(text: str) -> str | None:
    lowered = text.lower().replace("\n", " ")
    if "экзам" in lowered:
        return "exam"
    if "зач" in lowered and "оцен" in lowered:
        return "zachet_graded"
    if "зач" in lowered:
        return "zachet"
    if "курсов" in lowered and "проект" in lowered:
        return "kp"
    if "курсов" in lowered and "работ" in lowered:
        return "kr"
    return None


def _parse_assessment_semester(text: str) -> int | None:
    cleaned = text.strip().replace("\n", " ")
    match = re.search(r"(\d+)\s*/\s*(\d+)", cleaned)
    if match:
        return int(match.group(2))
    sem_m = re.search(r"(\d+)\s*сем", cleaned.lower())
    if sem_m:
        return int(sem_m.group(1))
    return None


def _split_assessment_form_parts(text: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[\n]+", text):
        for part in re.split(r",\s*", chunk):
            cleaned = part.strip(" /")
            if cleaned and cleaned not in {"-", "–", "—"}:
                parts.append(cleaned)
    return parts


def _expand_semester_token(token: str) -> list[int]:
    token = token.strip().strip("/")
    if not token:
        return []
    lowered = token.lower()
    sem_m = re.search(r"(\d+)\s*сем", lowered)
    if sem_m:
        return [int(sem_m.group(1))]
    match = re.search(r"(\d+)\s*/\s*([\d,\.]+)", token)
    if match:
        return [int(x) for x in re.findall(r"\d+", match.group(2))]
    single = _parse_assessment_semester(token)
    return [single] if single is not None else []


def _parse_assessment_semester_groups(text: str) -> list[list[int]]:
    groups: list[list[int]] = []
    for chunk in re.split(r"[\n]+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if re.search(r"\s/\s", chunk):
            parts = [part.strip() for part in re.split(r"\s*/\s*", chunk) if part.strip()]
        else:
            parts = [chunk]
        for part in parts:
            sems = _expand_semester_token(part)
            if sems:
                groups.append(sems)
    return groups


def _pair_assessment_forms_semesters(
    form_types: list[str],
    sem_groups: list[list[int]],
) -> list[tuple[str, int | None]]:
    pairs: list[tuple[str, int | None]] = []
    if not form_types:
        return pairs
    if sem_groups and len(form_types) == len(sem_groups):
        for form_type, sems in zip(form_types, sem_groups):
            for semester in sems:
                pairs.append((form_type, semester))
        return pairs
    flat_sems = [sem for group in sem_groups for sem in group]
    if form_types and flat_sems and len(form_types) == len(flat_sems):
        return list(zip(form_types, flat_sems))
    if form_types and len(sem_groups) == 1:
        for form_type in form_types:
            for semester in sem_groups[0]:
                pairs.append((form_type, semester))
        return pairs
    if form_types and len(flat_sems) == 1:
        return [(ft, flat_sems[0]) for ft in form_types]
    return [(ft, None) for ft in form_types]


def _extract_volume_assessments(doc: Document) -> list[dict]:
    """Формы аттестации из табл. 1.3 (ИЛИП: строка «Форма промежуточной аттестации»)."""
    items: list[dict] = []
    seen: set[tuple[str, int | None]] = set()

    for table in doc.tables:
        if len(table.rows) < 3:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = " ".join(c.text for c in table.rows[1].cells).lower()
        if _classify_table(header, second) != "volume_13":
            continue

        for row in table.rows[2:]:
            cells = [cell.text.strip() for cell in row.cells]
            if not cells:
                continue
            label = cells[0].lower().replace("\n", " ")
            if "форма" not in label or "аттест" not in label:
                continue
            if len(cells) < 2:
                continue

            form_parts = _split_assessment_form_parts(cells[1])
            form_types = [ft for p in form_parts if (ft := _parse_assessment_form_type(p))]
            sem_groups = _parse_assessment_semester_groups(cells[2]) if len(cells) > 2 else []
            pairs = _pair_assessment_forms_semesters(form_types, sem_groups)

            for form_type, semester in pairs:
                key = (form_type, semester)
                if key not in seen:
                    seen.add(key)
                    items.append({"form_type": form_type, "semester": semester})
        if items:
            break

    return items


def _extract_topics31_assessments(doc: Document) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, int | None]] = set()
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_table(header, second) != "topics_31":
            continue
        sem_cols: dict[int, tuple[str, int]] = {}
        for row in table.rows[:3]:
            for idx, cell in enumerate(row.cells):
                text = cell.text.lower().replace("\n", " ")
                sem_m = re.search(r"(\d+)\s*сем", text)
                if not sem_m:
                    continue
                semester = int(sem_m.group(1))
                if "экзам" in text or text.strip() in {"эк", "э"}:
                    sem_cols[idx] = ("exam", semester)
                elif "зач" in text and "оцен" in text:
                    sem_cols[idx] = ("zachet_graded", semester)
                elif "зач" in text or text.strip() in {"за", "з"}:
                    sem_cols[idx] = ("zachet", semester)
                elif "курсов" in text and "проект" in text:
                    sem_cols[idx] = ("kp", semester)
                elif "курсов" in text and "работ" in text:
                    sem_cols[idx] = ("kr", semester)
        if not sem_cols:
            continue
        for row in table.rows[2:]:
            cells = [c.text.strip() for c in row.cells]
            if not cells or "итого" in cells[0].lower():
                continue
            for idx, (form_type, semester) in sem_cols.items():
                if idx >= len(cells):
                    continue
                val = cells[idx].strip().lower()
                if not val or val in {"-", "–", "—", "0", "нет"}:
                    continue
                if val in {"+", "есть", "да", "v"} or _parse_int_cell(val) is not None:
                    key = (form_type, semester)
                    if key not in seen:
                        seen.add(key)
                        items.append({"form_type": form_type, "semester": semester})
    return items


def _cell_bold_title(cell) -> str | None:
    parts: list[str] = []
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            if run.bold and run.text.strip():
                parts.append(run.text.strip())
    if parts:
        return " ".join(parts)
    text = cell.text.strip()
    return text.split("\n")[0][:120] if text else None


def _extract_bold_topic_titles(doc: Document) -> list[dict]:
    titles: list[dict] = []
    seen: set[int] = set()
    for table in doc.tables:
        if len(table.rows) < 3:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = " ".join(c.text for c in table.rows[1].cells).lower()
        kind = _classify_table(header, second)
        if kind not in {"topics_31", "topics_detail", "matrix_36"}:
            if not _classify_matrix_table(header, second):
                continue
        for row in table.rows[2:]:
            cells = row.cells
            if not cells:
                continue
            num_text = cells[0].text.strip()
            match = TOPIC_NUM_RE.match(num_text)
            if not match:
                continue
            num = int(match.group(1))
            if num in seen:
                continue
            title_cell = cells[1] if len(cells) > 1 else cells[0]
            title = _cell_bold_title(title_cell)
            if title:
                seen.add(num)
                titles.append({"topic": num, "title": title, "bold": True})
    return titles


def extract_tz_fields(doc: Document, discipline_name: str | None = None) -> TzExtract:
    section2 = _extract_section2_zuv(doc, discipline_name)
    topics31_zuv = _extract_topics31_zuv(doc)
    flag_violations, flags_scanned = _extract_topics31_flags(doc)
    topic_numbers, topic_names = _extract_topic_summaries(doc)
    sr_rows, has_hw, has_current, ctrl_h, kr_h, kp_h, sr_total_tz = _extract_sr_rows_extended(doc)
    questions, q_total = _extract_sr_questions(doc)
    matrix_rows, matrix_totals = _extract_matrix_36(doc)
    pk_ok, pk_missing = _extract_pk_groups(doc)
    topics31_assess = _extract_topics31_assessments(doc)
    if not topics31_assess:
        topics31_assess = _extract_volume_assessments(doc)
    bold_titles = _extract_bold_topic_titles(doc)

    return TzExtract(
        section2_zuv_by_indicator=section2,
        topics31_zuv_phrases=topics31_zuv,
        topics31_flag_hour_violations=flag_violations,
        topics31_has_flag_columns=flags_scanned,
        topics31_assessments=topics31_assess,
        topic_titles_bold=bold_titles,
        topic_numbers=topic_numbers,
        topic_names=topic_names,
        sr_rows=sr_rows,
        sr_has_homework_control=has_hw,
        sr_has_current_control=has_current,
        sr_control_work_hours=ctrl_h,
        sr_course_work_hours_35=kr_h,
        sr_course_project_hours_35=kp_h,
        sr_questions=questions,
        sr_questions_hours_total=q_total,
        sr_self_study_budget_hours=_sr_self_study_budget(sr_rows),
        sr_table_total_from_rows=sr_total_tz,
        matrix_36_rows=matrix_rows,
        matrix_36_col_totals=matrix_totals,
        pk_indicators_without_group=pk_missing,
        pk_groups_ok=pk_ok,
    )


def merge_tz_into_rpd_dict(data: dict, tz: TzExtract) -> dict:
    """Слить TzExtract в dict для RpdExtract (additive)."""
    data.update(
        {
            "section2_zuv_by_indicator": tz.section2_zuv_by_indicator,
            "topics31_zuv_phrases": tz.topics31_zuv_phrases,
            "topics31_flag_hour_violations": tz.topics31_flag_hour_violations,
            "topics31_has_flag_columns": tz.topics31_has_flag_columns,
            "topics31_assessments": tz.topics31_assessments,
            "topic_titles_bold": tz.topic_titles_bold,
            "topic_numbers": tz.topic_numbers,
            "topic_names": tz.topic_names,
            "sr_rows": tz.sr_rows,
            "sr_has_homework_control": tz.sr_has_homework_control,
            "sr_has_current_control": data.get("sr_has_current_control") or tz.sr_has_current_control,
            "sr_control_work_hours": tz.sr_control_work_hours,
            "sr_table_total": tz.sr_table_total_from_rows or data.get("sr_table_total"),
            "sr_course_work_hours_35": tz.sr_course_work_hours_35,
            "sr_course_project_hours_35": tz.sr_course_project_hours_35,
            "sr_questions": tz.sr_questions,
            "sr_questions_hours_total": tz.sr_questions_hours_total,
            "sr_self_study_budget_hours": tz.sr_self_study_budget_hours,
            "matrix_36_rows": tz.matrix_36_rows,
            "matrix_36_col_totals": tz.matrix_36_col_totals,
            "pk_indicators_without_group": tz.pk_indicators_without_group,
            "pk_groups_ok": tz.pk_groups_ok,
        }
    )
    return data
