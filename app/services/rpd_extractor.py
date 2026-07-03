"""Извлечение данных РПД из DOCX для валидации (паспорт + таблица 1.3)."""

from __future__ import annotations

import io
import json
import re
from dataclasses import asdict, dataclass, field

from docx import Document

from app.utils.discipline_code import (
    DISCIPLINE_CODE_RE,
    extract_passport_from_docx,
    resolve_discipline_code,
)

COMPETENCY_CODE_RE = re.compile(r"(?:УК|ОПК|ПК|ПСК)-\d+(?:\.\d+)?", re.IGNORECASE)
INDICATOR_CODE_RE = re.compile(r"(?:УК|ОПК|ПК|ПСК)-\d+\.\d+", re.IGNORECASE)
DEPT_FROM_FILENAME_RE = re.compile(r"_k(\d+)", re.IGNORECASE)
DIRECTION_CODE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{2})")


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
    zuv_texts: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | None) -> RpdExtract | None:
        if not raw:
            return None
        data = json.loads(raw)
        volume_data = data.pop("volume", {}) or {}
        return cls(volume=VolumeBreakdown(**volume_data), **data)


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


def _extract_competencies(doc: Document) -> list[str]:
    codes: set[str] = set()
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
        for row in table.rows:
            for cell in row.cells:
                for match in COMPETENCY_CODE_RE.finditer(cell.text):
                    codes.add(match.group(0).upper())
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

    direction_code = None
    direction_raw = passport.get("direction_raw", "")
    direction_match = DIRECTION_CODE_RE.search(direction_raw)
    if direction_match:
        direction_code = direction_match.group(1)

    topics_contact, topics_lectures, topics_practical = _extract_topics_hours(doc, volume)

    return RpdExtract(
        discipline_code=code,
        discipline_name=_discipline_name_from_passport(passport),
        direction_code=direction_code,
        profile_name=passport.get("profile_name"),
        department_code=_department_from_filename(filename),
        discipline_head=discipline_head,
        director_name=director_name,
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
