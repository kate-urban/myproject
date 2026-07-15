"""Извлечение данных РПД из DOCX для валидации (паспорт + таблица 1.3)."""

from __future__ import annotations

import io
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Iterable

from docx import Document

from app.utils.discipline_code import (
    DISCIPLINE_CODE_RE,
    extract_passport_from_docx,
    resolve_discipline_code,
)

COMPETENCY_CODE_RE = re.compile(r"(?:УК|ОПК|ПК|ПСК)-\d+(?:\.\d+)?", re.IGNORECASE)
INDICATOR_CODE_RE = re.compile(r"(?:УК|ОПК|ПК|ПСК)-\d+\.\d+", re.IGNORECASE)
COMPETENCY_GROUP_RE = re.compile(r"((?:УК|ОПК|ПК|ПСК)-\d+)", re.IGNORECASE)
_UNICODE_DASHES = ("\u2013", "\u2014", "\u2212", "\u2011")
DEPT_FROM_FILENAME_RE = re.compile(r"_k(\d+)", re.IGNORECASE)


def normalize_competency_text(text: str) -> str:
    for ch in _UNICODE_DASHES:
        text = text.replace(ch, "-")
    return text


def normalize_competency_code(code: str) -> str:
    code = normalize_competency_text(code.strip()).upper()
    code = re.sub(r"^UK-", "УК-", code)
    code = re.sub(r"^OPK-", "ОПК-", code)
    code = re.sub(r"^PK-", "ПК-", code)
    code = re.sub(r"^PSK-", "ПСК-", code)
    return code


from app.utils.text import html_to_plain_text


def extract_competency_codes_from_text(text: str) -> set[str]:
    """Коды УК/ОПК/ПК из произвольного текста (HTML раздела, таблица и т.д.)."""
    if not text:
        return set()
    normalized = normalize_competency_text(text)
    codes: set[str] = set()
    for match in INDICATOR_CODE_RE.finditer(normalized):
        codes.add(normalize_competency_code(match.group(0)))
    for match in COMPETENCY_CODE_RE.finditer(normalized):
        code = normalize_competency_code(match.group(0))
        if INDICATOR_CODE_RE.fullmatch(code):
            codes.add(code)
    groups = {
        normalize_competency_code(match.group(1))
        for match in COMPETENCY_GROUP_RE.finditer(normalized)
    }
    for parent in groups:
        for bare in _bare_indicators_with_parent(parent, normalized):
            codes.add(normalize_competency_code(bare))
    return codes


DIRECTION_CODE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{2})")
DATE_DOT_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(20\d{2})\b")
YEAR_WITH_G_RE = re.compile(r"(20\d{2})\s*г\.?", re.IGNORECASE)
REAPPROVAL_ACADEMIC_YEAR_RE = re.compile(
    r"на\s+(20\d{2})\s*/\s*(20\d{2})\s*учеб",
    re.IGNORECASE,
)
REAPPROVAL_PROTOCOL_YEAR_RE = re.compile(
    r"протокол(?:\s+изменений\s+на\s+(20\d{2})\s*/\s*(20\d{2})|[^\n]{0,120}(20\d{2})\s*г)",
    re.IGNORECASE,
)


@dataclass
class VolumeBreakdown:
    contact: int | None = None
    lectures: int | None = None
    practical: int | None = None
    lab: int | None = None
    sr: int | None = None
    control: int | None = None
    has_course_project: bool = False
    has_course_work: bool = False
    course_project_hours: int | None = None
    course_work_hours: int | None = None


@dataclass
class RpdExtract:
    discipline_code: str | None = None
    discipline_name: str | None = None
    direction_code: str | None = None
    profile_name: str | None = None
    department_code: str | None = None
    discipline_head: str | None = None
    director_name: str | None = None
    approval_year: int | None = None
    has_reapproval_section: bool = False
    reapproval_years: list[int] = field(default_factory=list)
    hours_total: int | None = None
    credits: float | None = None
    competencies: list[str] = field(default_factory=list)
    volume: VolumeBreakdown = field(default_factory=VolumeBreakdown)
    topics_contact_hours: int | None = None
    topics_lecture_hours: int | None = None
    topics_practical_hours: int | None = None
    sr_table_total: int | None = None
    course_project_hours: int | None = None
    sr_has_current_control: bool = False
    sr_has_practical_exercises: bool = False
    sr_has_homework_control: bool = False
    zuv_texts: list[str] = field(default_factory=list)
    # Поля ТЗ (R015–R019, R024–R027) — additive, не ломают старый JSON
    section2_zuv_by_indicator: dict[str, list[str]] = field(default_factory=dict)
    topics31_zuv_phrases: list[str] = field(default_factory=list)
    topics31_flag_hour_violations: list[str] = field(default_factory=list)
    topics31_has_flag_columns: bool = False
    topics31_assessments: list[dict] = field(default_factory=list)
    topic_titles_bold: list[dict] = field(default_factory=list)
    topic_numbers: list[int] = field(default_factory=list)
    topic_names: dict[int, str] = field(default_factory=dict)
    sr_rows: list[dict] = field(default_factory=list)
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

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | None) -> RpdExtract | None:
        if not raw:
            return None
        data = json.loads(raw)
        volume_data = data.pop("volume", {}) or {}
        for key, default in (
            ("section2_zuv_by_indicator", {}),
            ("topics31_zuv_phrases", []),
            ("topics31_flag_hour_violations", []),
            ("topic_numbers", []),
            ("topic_names", {}),
            ("sr_rows", []),
            ("sr_questions", []),
            ("matrix_36_rows", []),
            ("matrix_36_col_totals", {}),
            ("pk_indicators_without_group", []),
        ):
            data.setdefault(key, default)
        data.setdefault("sr_has_homework_control", False)
        data.setdefault("topics31_has_flag_columns", False)
        data.setdefault("topics31_assessments", [])
        data.setdefault("topic_titles_bold", [])
        data.setdefault("pk_groups_ok", None)
        if names := data.get("topic_names"):
            data["topic_names"] = {int(k): v for k, v in names.items()}
        return cls(volume=VolumeBreakdown(**volume_data), **data)


def enrich_rpd_competencies(rpd: RpdExtract, texts: Iterable[str]) -> RpdExtract:
    """Дополняет извлечённые компетенции кодами из текста разделов документа."""
    codes = {normalize_competency_code(code) for code in rpd.competencies}
    for key in rpd.section2_zuv_by_indicator:
        if key != "_ungrouped":
            codes.add(normalize_competency_code(key))
    for text in texts:
        codes.update(extract_competency_codes_from_text(text))
    return replace(rpd, competencies=sorted(codes))


def _has_topic_marker(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in ("темы", "тема", "№ тем", "разделы)", "раздел)")
    )


def _classify_table(header: str, second_row: str = "") -> str:
    full = f"{header} {second_row}".lower()
    if "вид учебных занятий" in full:
        return "volume_13"
    if "темы (разделы)" in full or "темы(разделы)" in full:
        return "topics_31"
    if _has_topic_marker(full) and (
        "лек" in second_row or "практ" in second_row or "лаб" in second_row
    ):
        return "topics_detail"
    if "этап" in full and "практик" in full:
        return "topics_practice"
    if "компетенц" in full:
        return "competencies"
    if "самостоятельной работы" in full and "трудо" in full:
        return "sr_35"
    if "согласовано" in full or "утвержда" in full:
        return "passport_signatures"
    return "other"


def _parse_int_cell(text: str) -> int | None:
    cleaned = text.replace("\n", " ").strip()
    if not cleaned or cleaned in {"-", "–", "—"}:
        return None
    match = re.search(r"(\d+)", cleaned)
    return int(match.group(1)) if match else None


def _parse_hours_credits_cell(text: str) -> tuple[int | None, float | None]:
    cleaned = text.replace("\n", " ").strip()
    match = re.search(r"(\d+)\s*/\s*(\d+(?:[.,]\d+)?)", cleaned)
    if match:
        hours = int(match.group(1))
        credits = float(match.group(2).replace(",", "."))
        return hours, credits
    return _parse_int_cell(cleaned), None


def _parse_float_cell(text: str) -> float | None:
    cleaned = text.replace("\n", " ").strip().replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not match:
        return None
    return float(match.group(1))


def _first_form_hours(cells: list[str]) -> int | None:
    for cell in cells[1:]:
        value = _parse_int_cell(cell)
        if value is not None:
            return value
    return None


def _extract_volume_13(doc: Document) -> tuple[int | None, float | None, VolumeBreakdown]:
    volume = VolumeBreakdown()
    hours_total: int | None = None
    credits: float | None = None

    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_table(header, second) != "volume_13":
            continue

        for row in table.rows[2:]:
            cells = [cell.text.strip() for cell in row.cells]
            if not cells:
                continue
            label = cells[0].lower().replace("\n", " ")
            value = _first_form_hours(cells)

            if label.strip().startswith("всего") or "всего по дисциплин" in label:
                for cell in cells[1:]:
                    parsed_hours, parsed_credits = _parse_hours_credits_cell(cell)
                    if parsed_hours is not None:
                        hours_total = parsed_hours
                        if parsed_credits is not None and "дисциплин" in label:
                            credits = parsed_credits
                        break
                continue

            if "контакт" in label and value is not None:
                volume.contact = value
            elif "лекц" in label:
                volume.lectures = value
            elif "практическ" in label or "семинар" in label:
                volume.practical = value
            elif "лабор" in label:
                volume.lab = value
            elif "самостоятель" in label and value is not None:
                volume.sr = value
            elif label.startswith("контроль") or (
                "контроль" in label and "текущ" not in label and value is not None
            ):
                volume.control = value
            elif "курсов" in label and "проект" in label:
                volume.has_course_project = True
                if value is not None:
                    volume.course_project_hours = value
            elif "курсов" in label and "работ" in label:
                volume.has_course_work = True
                if value is not None:
                    volume.course_work_hours = value

    return hours_total, credits, volume


def _extract_passport_credits(doc: Document) -> float | None:
    for table in doc.tables[:10]:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            if "объем дисциплины" not in label and "объём дисциплины" not in label:
                continue
            for cell in reversed(cells[1:]):
                value = _parse_float_cell(cell)
                if value is not None:
                    return value
    return None


def _competency_group(code: str) -> str | None:
    match = COMPETENCY_GROUP_RE.match(code.upper())
    return match.group(1) if match else None


def _indicator_codes_in_text(text: str) -> list[str]:
    return [match.group(0).upper() for match in INDICATOR_CODE_RE.finditer(text)]


def _unique_cell_texts(row) -> list[str]:
    seen: set[str] = set()
    texts: list[str] = []
    for cell in row.cells:
        cleaned = re.sub(r"\s+", " ", cell.text.strip())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            texts.append(cleaned)
    return texts


def _competency_table_column_hints(table) -> tuple[set[int], set[int]]:
    code_cols: set[int] = set()
    indicator_cols: set[int] = set()
    for row in table.rows[: min(3, len(table.rows))]:
        for idx, cell in enumerate(row.cells):
            label = cell.text.lower().replace("\n", " ")
            if "индикатор" in label or "показател" in label:
                indicator_cols.add(idx)
            if "компетенц" in label and ("код" in label or "наименование" in label):
                code_cols.add(idx)
    return code_cols, indicator_cols


def _bare_indicators_with_parent(parent: str, text: str) -> list[str]:
    """«УК-5» + текст «5.1 … 5.2 …» → УК-5.1, УК-5.2 (колонка индикаторов без префикса)."""
    match = COMPETENCY_GROUP_RE.match(parent.upper())
    if not match:
        return []
    kind, base = match.group(1).split("-", 1)
    found: list[str] = []
    pattern = re.compile(rf"(?<![\d.]){re.escape(base)}\.(\d+)(?![\d.])")
    for item in pattern.finditer(text):
        found.append(f"{kind}-{base}.{item.group(1)}")
    return found


def _collect_competency_codes_from_row(
    row,
    *,
    code_cols: set[int],
    indicator_cols: set[int],
    current_group: str | None,
) -> tuple[set[str], str | None]:
    codes: set[str] = set()
    cell_texts = _unique_cell_texts(row)
    if not cell_texts:
        return codes, current_group

    row_text = " ".join(cell_texts)
    indicator_parts: list[str] = []
    code_parts: list[str] = []

    seen_cells: set[str] = set()
    for idx, cell in enumerate(row.cells):
        cleaned = re.sub(r"\s+", " ", cell.text.strip())
        if not cleaned or cleaned in seen_cells:
            continue
        seen_cells.add(cleaned)
        if indicator_cols and idx in indicator_cols:
            indicator_parts.append(cleaned)
        elif code_cols and idx in code_cols:
            code_parts.append(cleaned)
        elif any(marker in cleaned.lower() for marker in ("знать:", "уметь:", "владеть:")):
            indicator_parts.append(cleaned)

    indicator_text = " ".join(indicator_parts) if indicator_parts else row_text
    code_text = " ".join(code_parts) if code_parts else row_text

    for match in INDICATOR_CODE_RE.finditer(indicator_text):
        codes.add(normalize_competency_code(match.group(0)))
    for match in INDICATOR_CODE_RE.finditer(row_text):
        codes.add(normalize_competency_code(match.group(0)))

    row_group = current_group
    for match in COMPETENCY_CODE_RE.finditer(code_text):
        code = normalize_competency_code(match.group(0))
        codes.add(code)
        if not INDICATOR_CODE_RE.fullmatch(code):
            row_group = _competency_group(code) or row_group

    parent = row_group
    for bare in _bare_indicators_with_parent(parent, indicator_text):
        codes.add(normalize_competency_code(bare))
    for bare in _bare_indicators_with_parent(parent, row_text):
        codes.add(normalize_competency_code(bare))

    return codes, row_group


def _extract_competencies(doc: Document) -> list[str]:
    codes: set[str] = set()
    current_group: str | None = None
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

        code_cols, indicator_cols = _competency_table_column_hints(table)
        for row in table.rows[1:]:
            row_codes, current_group = _collect_competency_codes_from_row(
                row,
                code_cols=code_cols,
                indicator_cols=indicator_cols,
                current_group=current_group,
            )
            codes.update(row_codes)

    return sorted(codes)


def _extract_zuv_texts(doc: Document) -> list[str]:
    texts: list[str] = []
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
            if any(marker in lowered for marker in ("знать:", "уметь:", "владеть:")):
                texts.append(re.sub(r"\s+", " ", row_text))
    return texts


def _topic_column_indices(table) -> tuple[int | None, int | None]:
    lec_idx: int | None = None
    prac_idx: int | None = None
    for row in table.rows[:3]:
        for idx, cell in enumerate(row.cells):
            label = cell.text.lower().replace("\n", " ").replace("-", "")
            if lec_idx is None and "лек" in label:
                lec_idx = idx
            if prac_idx is None and ("практ" in label or "семинар" in label):
                prac_idx = idx
    return lec_idx, prac_idx


def _row_label(cells: list[str]) -> str:
    return " ".join(cells[:2]).lower().replace("\n", " ")


def _extract_topics_hours(
    doc: Document,
    volume: VolumeBreakdown,
) -> tuple[int | None, int | None, int | None]:
    best: tuple[int | None, int | None, int | None] | None = None
    best_score = -1

    for table in doc.tables:
        if len(table.rows) < 3:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = " ".join(c.text for c in table.rows[1].cells).lower()
        kind = _classify_table(header, second)
        if kind not in {"topics_detail", "topics_31", "topics_practice"}:
            continue

        lec_idx, prac_idx = _topic_column_indices(table)
        if lec_idx is not None or prac_idx is not None:
            for row in table.rows[2:]:
                cells = [cell.text.strip() for cell in row.cells]
                if len(cells) < 2:
                    continue
                label = _row_label(cells)
                if "всего" not in label and "итого" not in label:
                    continue
                if "лекц" in label and "практ" not in label and prac_idx is not None:
                    continue
                lectures = _parse_int_cell(cells[lec_idx]) if lec_idx is not None else None
                practical = _parse_int_cell(cells[prac_idx]) if prac_idx is not None else None
                if lectures is None and practical is None:
                    continue
                contact = (lectures or 0) + (practical or 0)
                score = contact
                if volume.contact is not None and contact == volume.contact:
                    score += 1000
                if score > best_score:
                    best_score = score
                    best = (contact, lectures, practical)
            continue

        total: int | None = None
        for row in table.rows[2:]:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) < 2:
                continue
            label = cells[0].lower().replace("\n", " ")
            if "семестр" in label and not _parse_int_cell(cells[1]):
                continue
            if "итого" not in label:
                continue
            parsed = None
            for cell in cells[1:]:
                parsed = _parse_int_cell(cell)
                if parsed is not None:
                    break
            if parsed is None:
                continue
            if "практич" in label or "контакт" in label:
                total = parsed
            elif "лекц" in label:
                continue
            elif total is None:
                total = parsed
        if total is not None and (best is None or total > (best[0] or 0)):
            best = (total, total, None)

    return best or (None, None, None)


def _extract_sr_table(
    doc: Document,
) -> tuple[int | None, bool, bool, int | None]:
    total: int | None = None
    has_current_control = False
    has_practical_exercises = False
    course_project_hours: int | None = None

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

        running = 0
        for row in table.rows[2:]:
            cells = [cell.text.strip() for cell in row.cells]
            if not cells:
                continue
            label = cells[0].lower().replace("\n", " ")
            if "текущ" in label and "контрол" in label:
                has_current_control = True
            if "практическ" in label and "упражн" in label:
                has_practical_exercises = True
            if "итого" in label and "ср" in label:
                parsed = _first_form_hours(cells)
                if parsed is not None:
                    total = parsed
                continue
            value = _first_form_hours(cells)
            if value is not None:
                if "курсов" in label and "проект" in label:
                    course_project_hours = value
                running += value
        if total is None and running:
            total = running
        return total, has_current_control, has_practical_exercises, course_project_hours

    return None, has_current_control, has_practical_exercises, course_project_hours


def _years_in_signature_text(text: str) -> list[int]:
    years: list[int] = []
    for match in DATE_DOT_RE.finditer(text):
        years.append(int(match.group(1)))
    for match in YEAR_WITH_G_RE.finditer(text):
        year = int(match.group(1))
        if year not in years:
            years.append(year)
    return years


def _extract_approval_year(doc: Document) -> int | None:
    for table in doc.tables[:3]:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        if _classify_table(header) != "passport_signatures":
            continue
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if not text or "утвержда" not in text.lower():
                    continue
                years = _years_in_signature_text(text)
                if years:
                    return years[-1]
    return None


def _extract_reapproval_years(doc: Document) -> tuple[bool, list[int]]:
    full = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    marker = "сведения о переутвержден"
    idx = full.lower().find(marker)
    if idx < 0:
        return False, []

    section = full[idx:]
    years: set[int] = set()
    for match in REAPPROVAL_ACADEMIC_YEAR_RE.finditer(section):
        years.add(int(match.group(1)))
        years.add(int(match.group(2)))
    for match in REAPPROVAL_PROTOCOL_YEAR_RE.finditer(section):
        if match.group(1) and match.group(2):
            years.add(int(match.group(1)))
            years.add(int(match.group(2)))
        elif match.group(3):
            years.add(int(match.group(3)))
    return True, sorted(years)


def _extract_signatures(doc: Document) -> tuple[str | None, str | None]:
    director_name: str | None = None
    discipline_head: str | None = None

    for table in doc.tables[:3]:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        if _classify_table(header) != "passport_signatures":
            continue
        for row in table.rows:
            text = " ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            lowered = text.lower()
            if "утвержда" in lowered and not director_name:
                director_name = text
            if "руководител" in lowered and "дисциплин" in lowered:
                discipline_head = text
    return director_name, discipline_head


def _discipline_name_from_passport(passport: dict[str, str]) -> str | None:
    raw = passport.get("discipline_raw", "")
    code = passport.get("discipline_code")
    if not raw:
        return None
    if code and code in raw:
        name = raw.split(code, 1)[-1].strip(" :|")
        name = re.sub(r"^\s*[|:]\s*", "", name)
        if name and not re.fullmatch(r"[\d\s.,/з.е.]+", name, re.IGNORECASE):
            return name
    cleaned = raw.strip()
    match = DISCIPLINE_CODE_RE.search(cleaned)
    if match:
        name = cleaned[match.end() :].strip(" :|")
        if name:
            return name
    return cleaned or None


def _department_from_filename(filename: str) -> str | None:
    match = DEPT_FROM_FILENAME_RE.search(filename)
    return match.group(1) if match else None


def extract_rpd(file_bytes: bytes, filename: str = "upload.docx") -> RpdExtract:
    doc = Document(io.BytesIO(file_bytes))
    passport = extract_passport_from_docx(file_bytes)
    hours_total, volume_credits, volume = _extract_volume_13(doc)
    if hours_total is None and volume.practical is not None:
        hours_total = volume.practical + (volume.sr or 0) + (volume.control or 0)
    credits = volume_credits or _extract_passport_credits(doc)
    code = resolve_discipline_code(file_bytes, filename)
    sr_total, sr_current, sr_practical, course_project_hours = _extract_sr_table(doc)
    director_name, discipline_head = _extract_signatures(doc)
    approval_year = _extract_approval_year(doc)
    has_reapproval_section, reapproval_years = _extract_reapproval_years(doc)

    direction_code = None
    direction_raw = passport.get("direction_raw", "")
    direction_match = DIRECTION_CODE_RE.search(direction_raw)
    if direction_match:
        direction_code = direction_match.group(1)

    topics_contact, topics_lectures, topics_practical = _extract_topics_hours(doc, volume)

    from app.services.rpd_extract_tz import extract_tz_fields, merge_tz_into_rpd_dict

    discipline_name = _discipline_name_from_passport(passport)
    tz = extract_tz_fields(doc, discipline_name)
    result = RpdExtract(
        discipline_code=code,
        discipline_name=discipline_name,
        direction_code=direction_code,
        profile_name=passport.get("profile_name"),
        department_code=_department_from_filename(filename),
        discipline_head=discipline_head,
        director_name=director_name,
        approval_year=approval_year,
        has_reapproval_section=has_reapproval_section,
        reapproval_years=reapproval_years,
        hours_total=hours_total,
        credits=credits,
        competencies=_extract_competencies(doc),
        volume=volume,
        topics_contact_hours=topics_contact,
        topics_lecture_hours=topics_lectures,
        topics_practical_hours=topics_practical,
        sr_table_total=sr_total,
        course_project_hours=course_project_hours,
        sr_has_current_control=sr_current,
        sr_has_practical_exercises=sr_practical,
        zuv_texts=_extract_zuv_texts(doc),
    )
    base = asdict(result)
    merge_tz_into_rpd_dict(base, tz)
    volume_data = base.pop("volume", {}) or {}
    return RpdExtract(volume=VolumeBreakdown(**volume_data), **base)
