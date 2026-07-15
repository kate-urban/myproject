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

ZUV_MARKER_RE = re.compile(r"(знать|уметь|владеть)\s*:", re.IGNORECASE)
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
    sr_has_homework_control: bool = False
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
    return re.sub(r"\s+", " ", text.strip().lower())


def _split_zuv_phrases(text: str) -> list[str]:
    """Разбить текст З/У/В на отдельные формулировки."""
    if not text.strip():
        return []
    parts: list[str] = []
    markers = list(ZUV_MARKER_RE.finditer(text))
    if not markers:
        return [_normalize_phrase(text)] if text.strip() else []

    for idx, match in enumerate(markers):
        start = match.end()
        end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        chunk = text[start:end].strip(" ;,")
        if chunk:
            parts.append(_normalize_phrase(chunk))
    return parts


def _indicator_codes_in_text(text: str) -> list[str]:
    return [m.group(0).upper() for m in INDICATOR_CODE_RE.finditer(text)]


def _row_relevant_for_discipline(row_text: str, discipline_name: str | None) -> bool:
    """Если в строке несколько дисциплин — оставить только релевантные."""
    if not discipline_name:
        return True
    lowered = row_text.lower()
    if discipline_name.lower() not in lowered:
        other_markers = ("гидромелиора", "почвовед", "дисциплин")
        if any(m in lowered for m in other_markers) and ";" in row_text:
            return False
    return True


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
        for row in table.rows[1:]:
            row_text = " ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if not row_text or not ZUV_MARKER_RE.search(row_text):
                continue
            if not _row_relevant_for_discipline(row_text, discipline_name):
                continue
            codes = _indicator_codes_in_text(row_text)
            phrases = _split_zuv_phrases(row_text)
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
                if ZUV_MARKER_RE.search(row_text):
                    for phrase in _split_zuv_phrases(row_text):
                        if phrase not in seen:
                            seen.add(phrase)
                            phrases.append(phrase)
            continue
        for row in table.rows[2:]:
            cells = [c.text.strip() for c in row.cells]
            if zuv_col >= len(cells):
                continue
            cell_text = cells[zuv_col]
            if not ZUV_MARKER_RE.search(cell_text):
                continue
            for phrase in _split_zuv_phrases(cell_text):
                if phrase not in seen:
                    seen.add(phrase)
                    phrases.append(phrase)
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
            if not (_has_topic_marker(header) and "№ тем" in header):
                continue
            kind = "matrix_36"
        if kind == "topics_31" and "темы (разделы)" not in header:
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
    full = f"{header} {second}".lower()
    return ("№ тем" in full or "№ темы" in full) and (
        "объем работы" in full or "объём работы" in full or "лек" in second
    )


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


def _extract_sr_rows_extended(doc: Document) -> tuple[list[dict], bool, bool, int | None, int | None, int | None]:
    sr_rows: list[dict] = []
    has_homework = False
    has_current = False
    control_hours: int | None = None
    kr_hours: int | None = None
    kp_hours: int | None = None

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

        for row in table.rows[2:]:
            cells = [cell.text.strip() for cell in row.cells]
            if not cells:
                continue
            label = cells[0].lower().replace("\n", " ")
            if "итого" in label and "ср" in label:
                continue
            hours = _first_form_hours(cells)
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

    return sr_rows, has_current, has_homework, control_hours, kr_hours, kp_hours


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
    sr_rows, has_hw, _, ctrl_h, kr_h, kp_h = _extract_sr_rows_extended(doc)
    questions, q_total = _extract_sr_questions(doc)
    matrix_rows, matrix_totals = _extract_matrix_36(doc)
    pk_ok, pk_missing = _extract_pk_groups(doc)
    topics31_assess = _extract_topics31_assessments(doc)
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
        sr_control_work_hours=ctrl_h,
        sr_course_work_hours_35=kr_h,
        sr_course_project_hours_35=kp_h,
        sr_questions=questions,
        sr_questions_hours_total=q_total,
        sr_self_study_budget_hours=_sr_self_study_budget(sr_rows),
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
            "sr_control_work_hours": tz.sr_control_work_hours,
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
