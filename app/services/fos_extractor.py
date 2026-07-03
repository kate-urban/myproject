"""Извлечение данных ФОС из DOCX для валидации (паспорт + таблицы контроля)."""

from __future__ import annotations

import io
import json
import re
from dataclasses import asdict, dataclass, field

from docx import Document

from app.services.rpd_extractor import (
    COMPETENCY_CODE_RE,
    DEPT_FROM_FILENAME_RE,
    DIRECTION_CODE_RE,
    INDICATOR_CODE_RE,
)
from app.utils.discipline_code import (
    extract_passport_from_docx,
    resolve_discipline_code,
)

HEADER_DUPLICATE_RE = re.compile(
    r"^(текущий контроль|промежуточная аттестация|итого)$",
    re.IGNORECASE,
)


@dataclass
class FosControlItem:
    topic: str
    competency_code: str | None = None
    indicator_code: str | None = None
    assessment_form: str | None = None


@dataclass
class FosGradingCriterion:
    description: str
    grade_label: str | None = None
    points: str | None = None


@dataclass
class FosExtract:
    discipline_code: str | None = None
    discipline_name: str | None = None
    direction_code: str | None = None
    profile_name: str | None = None
    department_code: str | None = None
    competencies: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    control_items: list[FosControlItem] = field(default_factory=list)
    grading_criteria: list[FosGradingCriterion] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | None) -> FosExtract | None:
        if not raw:
            return None
        data = json.loads(raw)
        control_items = [FosControlItem(**item) for item in data.pop("control_items", [])]
        grading_criteria = [
            FosGradingCriterion(**item) for item in data.pop("grading_criteria", [])
        ]
        return cls(
            control_items=control_items,
            grading_criteria=grading_criteria,
            **data,
        )


def _classify_fos_table(header: str, second_row: str = "") -> str:
    full = f"{header} {second_row}".lower()
    if "контролируем" in full and ("раздел" in full or "тем" in full):
        return "fos_control"
    if "критери" in full and "оцен" in full:
        return "fos_grading"
    if header.strip().lower().startswith("дисциплин") or full.strip().startswith("дисциплин"):
        return "passport_discipline"
    if "направлен" in full and "профил" not in full:
        return "passport_direction"
    if "профиль" in full or "направленност" in full:
        return "passport_profile"
    if header.strip().lower().startswith("кафедра"):
        return "passport_department"
    if "компетенц" in full or "индикатор" in full or "показател" in full:
        return "fos_competencies"
    return "other"


def _first_code(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text)
    return match.group(0).upper() if match else None


def _codes_from_cell(text: str) -> list[str]:
    return sorted({match.group(0).upper() for match in COMPETENCY_CODE_RE.finditer(text)})


def _indicators_from_cell(text: str) -> list[str]:
    return sorted({match.group(0).upper() for match in INDICATOR_CODE_RE.finditer(text)})


def _discipline_name_from_passport(passport: dict[str, str]) -> str | None:
    raw = passport.get("discipline_raw", "")
    code = passport.get("discipline_code")
    if not raw:
        return None
    if code and code in raw:
        name = raw.split(code, 1)[-1].strip(" :|")
        name = re.sub(r"^\s*[|:]\s*", "", name)
        if name:
            return name
    return raw.strip() or None


def _extract_department(doc: Document) -> str | None:
    for table in doc.tables[:8]:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        if _classify_fos_table(header) != "passport_department":
            continue
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if len(cells) >= 2 and "кафедра" not in cells[-1].lower():
                return cells[-1]
    return None


def _extract_competencies_and_indicators(doc: Document) -> tuple[list[str], list[str]]:
    competencies: set[str] = set()
    indicators: set[str] = set()
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_fos_table(header, second) != "fos_competencies":
            continue
        for row in table.rows[1:]:
            row_text = " ".join(cell.text for cell in row.cells)
            competencies.update(_codes_from_cell(row_text))
            indicators.update(_indicators_from_cell(row_text))
    return sorted(competencies), sorted(indicators)


def _is_control_header_row(cells: list[str]) -> bool:
    if not cells:
        return True
    joined = " ".join(cells).lower().replace("\n", " ")
    if HEADER_DUPLICATE_RE.search(cells[0].strip()):
        return True
    if "контролируем" in joined and "компетенц" in joined:
        return True
    if all(part == cells[0].strip() for part in cells if part.strip()):
        return True
    return False


def _extract_control_items(doc: Document) -> list[FosControlItem]:
    items: list[FosControlItem] = []
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        second = (
            " ".join(c.text for c in table.rows[1].cells).lower()
            if len(table.rows) > 1
            else ""
        )
        if _classify_fos_table(header, second) != "fos_control":
            continue
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) < 2 or _is_control_header_row(cells):
                continue
            topic = cells[1] if len(cells) > 1 else cells[0]
            if not topic or HEADER_DUPLICATE_RE.search(topic):
                continue
            competency = _first_code(cells[2], COMPETENCY_CODE_RE) if len(cells) > 2 else None
            indicator = _first_code(cells[3], INDICATOR_CODE_RE) if len(cells) > 3 else None
            assessment = cells[4] if len(cells) > 4 else None
            items.append(
                FosControlItem(
                    topic=topic,
                    competency_code=competency,
                    indicator_code=indicator,
                    assessment_form=assessment,
                )
            )
    return items


def _extract_grading_criteria(doc: Document) -> list[FosGradingCriterion]:
    criteria: list[FosGradingCriterion] = []
    for table in doc.tables:
        if not table.rows:
            continue
        header = " ".join(c.text for c in table.rows[0].cells).lower()
        if _classify_fos_table(header) != "fos_grading":
            continue
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if len(cells) < 2:
                continue
            if "критери" in cells[0].lower() and "оцен" in " ".join(cells).lower():
                continue
            description = cells[1] if len(cells) > 1 else cells[0]
            grade_label = cells[2] if len(cells) > 2 else None
            points = cells[3] if len(cells) > 3 else None
            if description:
                criteria.append(
                    FosGradingCriterion(
                        description=description.replace("\n", " "),
                        grade_label=grade_label,
                        points=points,
                    )
                )
    return criteria


def extract_fos(file_bytes: bytes, filename: str = "upload.docx") -> FosExtract:
    doc = Document(io.BytesIO(file_bytes))
    passport = extract_passport_from_docx(file_bytes)
    competencies, indicators = _extract_competencies_and_indicators(doc)

    direction_code = None
    direction_raw = passport.get("direction_raw", "")
    direction_match = DIRECTION_CODE_RE.search(direction_raw)
    if direction_match:
        direction_code = direction_match.group(1)

    dept_match = DEPT_FROM_FILENAME_RE.search(filename)
    department_code = dept_match.group(1) if dept_match else None

    return FosExtract(
        discipline_code=resolve_discipline_code(file_bytes, filename),
        discipline_name=_discipline_name_from_passport(passport),
        direction_code=direction_code,
        profile_name=passport.get("profile_name"),
        department_code=department_code,
        competencies=competencies,
        indicators=indicators,
        control_items=_extract_control_items(doc),
        grading_criteria=_extract_grading_criteria(doc),
    )
