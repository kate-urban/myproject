"""Детерминированные предложения правок для ошибок сверки (уровень 2)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape

from bs4 import BeautifulSoup

from app.models import PlanDiscipline, StudyPlan
from app.services.rpd_extractor import DIRECTION_CODE_RE, RpdExtract, VolumeBreakdown
from app.services.validation.rules import RuleResult, ValidationContext
from app.utils.discipline_code import DISCIPLINE_CODE_RE

SUPPORTED_RULE_IDS = frozenset(
    {"R001", "R002", "R003", "R004", "R005", "R020", "R021", "R022", "R025"}
)


@dataclass
class FixChange:
    field: str
    old: str
    new: str
    row_label: str | None = None


@dataclass
class SuggestFixResult:
    rule_id: str
    supported: bool
    apply_safe: bool
    patched_html: str | None = None
    changes: list[FixChange] = field(default_factory=list)
    message: str = ""
    source: str = "deterministic"
    explanation: str | None = None


def _cell_text(cell) -> str:
    return cell.get_text(" ", strip=True)


def _set_cell_text(cell, text: str) -> None:
    cell.clear()
    cell.append(BeautifulSoup(f"<p>{escape(text)}</p>", "html.parser").p)


def _iter_rows(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if cells:
                yield table, tr, cells


def _row_label(cells) -> str:
    if not cells:
        return ""
    first = _cell_text(cells[0])
    if re.match(r"^\d+\.?\s*$", first.replace(" ", "")) and len(cells) > 1:
        return _cell_text(cells[1]).lower()
    return first.lower()


def _find_row(soup: BeautifulSoup, *keywords: str, exclude: tuple[str, ...] = ()) -> tuple | None:
    for _table, tr, cells in _iter_rows(soup):
        label = _row_label(cells)
        if not label:
            continue
        if any(ex in label for ex in exclude):
            continue
        if all(kw in label for kw in keywords):
            return tr, cells
    return None


def _value_cell(cells, col: int = 1):
    if len(cells) <= col:
        return None
    return cells[col]


def _volume_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        header = table.get_text(" ", strip=True).lower()
        if "вид учебных" in header:
            return table
    return None


def _volume_row(table, *keywords: str, exclude: tuple[str, ...] = ()):
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = _row_label(cells)
        if any(ex in label for ex in exclude):
            continue
        if all(kw in label for kw in keywords):
            return tr, cells
    return None, None


def _patch_cell(tr, cells, col: int, new_text: str, field: str, row_label: str) -> FixChange | None:
    cell = _value_cell(cells, col)
    if cell is None:
        return None
    old = _cell_text(cell)
    if old == new_text:
        return None
    _set_cell_text(cell, new_text)
    return FixChange(field=field, old=old, new=new_text, row_label=row_label)


def _replace_code_in_text(text: str, expected: str, actual: str | None, code_re: re.Pattern[str]) -> str:
    if actual and actual in text:
        return text.replace(actual, expected, 1)
    match = code_re.search(text)
    if match:
        return code_re.sub(expected, text, count=1)
    return f"{expected} {text}".strip()


def _fix_passport_code(
    soup: BeautifulSoup,
    expected: str,
    actual: str | None,
) -> FixChange | None:
    found = _find_row(soup, "дисциплин", exclude=("направлен",))
    if not found:
        found = _find_row(soup, "шифр")
    if not found:
        return None
    tr, cells = found
    cell = _value_cell(cells, 1) or _value_cell(cells, -1)
    if cell is None:
        return None
    old = _cell_text(cell)
    new = _replace_code_in_text(old, expected, actual, DISCIPLINE_CODE_RE)
    if new == old:
        return None
    _set_cell_text(cell, new)
    return FixChange(field="discipline_code", old=old, new=new, row_label=_row_label(cells))


def _fix_passport_direction(
    soup: BeautifulSoup,
    expected: str,
    actual: str | None,
) -> FixChange | None:
    found = _find_row(soup, "направлен", exclude=("профил", "направленност"))
    if not found:
        return None
    tr, cells = found
    cell = _value_cell(cells, 1) or cells[-1]
    old = _cell_text(cell)
    new = _replace_code_in_text(old, expected, actual, DIRECTION_CODE_RE)
    if new == old:
        return None
    _set_cell_text(cell, new)
    return FixChange(field="direction_code", old=old, new=new, row_label=_row_label(cells))


def _fix_passport_text_field(
    soup: BeautifulSoup,
    keywords: tuple[str, ...],
    exclude: tuple[str, ...],
    expected: str,
    actual: str | None,
    field: str,
) -> FixChange | None:
    found = _find_row(soup, *keywords, exclude=exclude)
    if not found:
        return None
    tr, cells = found
    cell = _value_cell(cells, 1) or cells[-1]
    old = _cell_text(cell)
    if actual and actual in old and expected:
        new = old.replace(actual, expected, 1)
    elif expected:
        new = expected
    else:
        return None
    if new == old:
        return None
    _set_cell_text(cell, new)
    return FixChange(field=field, old=old, new=new, row_label=_row_label(cells))


def _fix_discipline_name(
    soup: BeautifulSoup,
    expected: str,
    actual: str | None,
) -> FixChange | None:
    found = _find_row(soup, "дисциплин", exclude=("направлен",))
    if not found:
        return None
    tr, cells = found
    cell = _value_cell(cells, 1) or cells[-1]
    old = _cell_text(cell)
    code_match = DISCIPLINE_CODE_RE.search(old)
    code = code_match.group(0) if code_match else ""
    if actual and _normalize_loose(actual) in _normalize_loose(old):
        remainder = old
        for token in DISCIPLINE_CODE_RE.findall(old):
            remainder = remainder.replace(token, " ")
        remainder = re.sub(r"\s+", " ", remainder).strip(" ,;-")
        new = f"{code} {expected}".strip() if code else expected
    elif code:
        new = f"{code} {expected}".strip()
    else:
        new = expected
    if new == old:
        return None
    _set_cell_text(cell, new)
    return FixChange(field="discipline_name", old=old, new=new, row_label=_row_label(cells))


def _normalize_loose(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _parse_hours_credits(text: str) -> tuple[int | None, float | None]:
    match = re.search(r"(\d+)\s*/\s*(\d+(?:[.,]\d+)?)", text)
    if match:
        return int(match.group(1)), float(match.group(2).replace(",", "."))
    num = re.search(r"(\d+)", text)
    return (int(num.group(1)), None) if num else (None, None)


def _format_hours_credits(hours: int | None, credits: float | None, template: str) -> str:
    if hours is not None and credits is not None and "/" in template:
        credit_str = str(int(credits)) if credits == int(credits) else str(credits)
        return f"{hours}/{credit_str}"
    if hours is not None:
        return str(hours)
    if credits is not None:
        credit_str = str(int(credits)) if credits == int(credits) else str(credits)
        return credit_str
    return template


def _fix_volume_hours(
    soup: BeautifulSoup,
    row_keywords: tuple[str, ...],
    new_hours: int,
    field: str,
    exclude: tuple[str, ...] = (),
) -> FixChange | None:
    table = _volume_table(soup)
    if table is None:
        return None
    tr, cells = _volume_row(table, *row_keywords, exclude=exclude)
    if not cells:
        return None
    cell = _value_cell(cells, 1)
    if cell is None:
        return None
    old = _cell_text(cell)
    hours, credits = _parse_hours_credits(old)
    new_text = _format_hours_credits(new_hours, credits, old)
    return _patch_cell(tr, cells, 1, new_text, field, _row_label(cells))


def _fix_total_credits(soup: BeautifulSoup, credits: float) -> FixChange | None:
    table = _volume_table(soup)
    if table is None:
        return None
    tr, cells = _volume_row(table, "всего")
    if not cells:
        return None
    cell = _value_cell(cells, 1)
    if cell is None:
        return None
    old = _cell_text(cell)
    hours, _old_credits = _parse_hours_credits(old)
    new_text = _format_hours_credits(hours, credits, old)
    return _patch_cell(tr, cells, 1, new_text, "credits", _row_label(cells))


def _read_volume_hours(vol: VolumeBreakdown) -> dict[str, int | None]:
    return {
        "lectures": None if vol.lectures_not_in_plan else vol.lectures,
        "practical": None if vol.practical_not_in_plan else vol.practical,
        "lab": None if vol.lab_not_in_plan else vol.lab,
        "contact": None if vol.contact_not_in_plan else vol.contact,
        "sr": None if vol.sr_not_in_plan else vol.sr,
    }


def _fix_r025_breakdown(soup: BeautifulSoup, contact: int, vol: VolumeBreakdown) -> list[FixChange]:
    table = _volume_table(soup)
    if table is None:
        return []
    hours = _read_volume_hours(vol)
    parts = {
        "lectures": ("лекц", hours["lectures"] or 0),
        "practical": ("практическ", hours["practical"] or 0),
        "lab": ("лабор", hours["lab"] or 0),
    }
    current_sum = sum(v for _, v in parts.values())
    if current_sum == contact:
        return []
    delta = contact - current_sum
    # Увеличить наибольшую ненулевую строку (или практику)
    target_key = max(parts, key=lambda k: parts[k][1]) if any(parts[k][1] for k in parts) else "practical"
    changes: list[FixChange] = []
    for key, (kw, value) in parts.items():
        if key != target_key:
            continue
        tr, cells = _volume_row(table, kw)
        if not cells:
            continue
        new_val = max(0, value + delta)
        change = _patch_cell(tr, cells, 1, str(new_val), key, _row_label(cells))
        if change:
            changes.append(change)
        break
    return changes


def _fix_r021_minimum(soup: BeautifulSoup, vol: VolumeBreakdown, expected_min: int, kind: str) -> FixChange | None:
    table = _volume_table(soup)
    if table is None:
        return None
    if kind == "kp":
        tr, cells = _volume_row(table, "курсов", exclude=("работ",))
        if not cells:
            tr, cells = _volume_row(table, "курсов", "проект")
        field = "course_project_hours"
    else:
        tr, cells = _volume_row(table, "курсов", "работ")
        field = "course_work_hours"
    if not cells:
        return None
    return _patch_cell(tr, cells, 1, str(expected_min), field, _row_label(cells))


def suggest_validation_fix(
    rule_id: str,
    section_html: str,
    ctx: ValidationContext,
    rule_result: RuleResult,
) -> SuggestFixResult:
    """Сформировать правку HTML раздела по результату правила."""
    rule_id = (rule_id or "").upper()
    if rule_id not in SUPPORTED_RULE_IDS:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=False,
            apply_safe=False,
            message=f"Автоправка для {rule_id} пока не поддерживается",
        )
    if rule_result.passed or rule_result.skipped:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=False,
            apply_safe=False,
            message="Правило уже выполнено или пропущено",
        )

    soup = BeautifulSoup(section_html or "", "html.parser")
    changes: list[FixChange] = []
    apply_safe = True

    if rule_id == "R001":
        change = _fix_passport_code(soup, ctx.discipline.code, rule_result.actual)
        if change:
            changes.append(change)
    elif rule_id == "R002":
        change = _fix_passport_direction(soup, ctx.direction_code, rule_result.actual)
        if change:
            changes.append(change)
    elif rule_id == "R003":
        change = _fix_passport_text_field(
            soup,
            ("профиль",),
            ("направлен",),
            ctx.profile_name or rule_result.expected or "",
            rule_result.actual,
            "profile_name",
        )
        if change:
            changes.append(change)
    elif rule_id == "R004":
        change = _fix_discipline_name(soup, ctx.discipline.name, rule_result.actual)
        if change:
            changes.append(change)
    elif rule_id == "R005":
        if ctx.discipline.credits is not None:
            change = _fix_total_credits(soup, float(ctx.discipline.credits))
            if change:
                changes.append(change)
    elif rule_id == "R020":
        if rule_result.message and "СР в РПД" in rule_result.message:
            if rule_result.expected and rule_result.expected.isdigit():
                change = _fix_volume_hours(soup, ("самостоятель",), int(rule_result.expected), "sr_hours")
                if change:
                    changes.append(change)
        elif rule_result.expected and rule_result.expected.isdigit():
            change = _fix_volume_hours(soup, ("всего",), int(rule_result.expected), "hours_total")
            if change:
                changes.append(change)
    elif rule_id == "R021":
        expected_min = 40 if rule_result.expected and "40" in rule_result.expected else 30
        kind = "kp" if ctx.rpd.volume.has_course_project else "kr"
        change = _fix_r021_minimum(soup, ctx.rpd.volume, expected_min, kind)
        if change:
            changes.append(change)
    elif rule_id == "R022":
        if ctx.rpd.volume.contact_not_in_plan:
            return SuggestFixResult(
                rule_id=rule_id,
                supported=False,
                apply_safe=False,
                message="Строка «не предусмотрено учебным планом» — правку нужно сделать вручную",
            )
        if rule_result.expected and rule_result.expected.isdigit():
            keywords = ("контакт",) if str(ctx.discipline.object_type) != "3" else ("практическ",)
            change = _fix_volume_hours(soup, keywords, int(rule_result.expected), "contact_hours")
            if change:
                changes.append(change)
    elif rule_id == "R025":
        if ctx.rpd.volume.contact_not_in_plan:
            return SuggestFixResult(
                rule_id=rule_id,
                supported=False,
                apply_safe=False,
                message="Контакт отмечен как не предусмотренный планом — автоправка недоступна",
            )
        contact = int(rule_result.expected) if rule_result.expected and rule_result.expected.isdigit() else None
        if contact is not None:
            changes.extend(_fix_r025_breakdown(soup, contact, ctx.rpd.volume))

    if not changes:
        return SuggestFixResult(
            rule_id=rule_id,
            supported=True,
            apply_safe=False,
            message="Не удалось найти в HTML раздела таблицу или строку для правки",
        )

    return SuggestFixResult(
        rule_id=rule_id,
        supported=True,
        apply_safe=apply_safe,
        patched_html=str(soup),
        changes=changes,
        message=f"Предложено изменений: {len(changes)}",
    )
