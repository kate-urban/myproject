"""Правила валидации ФОС ↔ учебный план ↔ РПД (шаг 3, F001–F014)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.models import PlanDiscipline
from app.services.fos_extractor import FosExtract
from app.services.rpd_extractor import INDICATOR_CODE_RE, RpdExtract
from app.services.validation.rules import RuleResult, _normalize_code, _texts_match

RuleFn = Callable[["FosValidationContext"], RuleResult]

FOS_UP_RULE_IDS = [
    "F001",
    "F002",
    "F003",
    "F006",
    "F007",
    "F009",
    "F010",
    "F011",
    "F012",
    "F013",
    "F014",
]

FOS_RPD_RULE_IDS = [
    "F004",
    "F005",
    "F008",
]

DEFAULT_FOS_ONLY_RULE_IDS = FOS_UP_RULE_IDS

DEFAULT_FOS_RULE_IDS = FOS_UP_RULE_IDS + FOS_RPD_RULE_IDS + ["F015"]

_PROFILE_BOILERPLATE_RE = re.compile(
    r"^(направленность\s*\(?\s*профиль\s*\)?|профиль|направление\s*подготовки)$",
    re.IGNORECASE,
)


@dataclass
class FosValidationContext:
    direction_code: str
    direction_name: str
    profile_name: str
    discipline: PlanDiscipline
    rpd: RpdExtract
    fos: FosExtract


def _plan_indicators(discipline: PlanDiscipline) -> set[str]:
    return {item.competency_code.upper() for item in discipline.competencies}


def _fos_indicators(fos: FosExtract) -> set[str]:
    codes = set(fos.indicators)
    for code in fos.competencies:
        if INDICATOR_CODE_RE.fullmatch(code.upper()):
            codes.add(code.upper())
    for item in fos.control_items:
        if item.indicator_code:
            codes.add(item.indicator_code.upper())
    return codes


def _rpd_indicators(rpd: RpdExtract) -> set[str]:
    return {code.upper() for code in rpd.competencies if INDICATOR_CODE_RE.fullmatch(code.upper())}


def _profile_segments(value: str | None) -> list[str]:
    if not value:
        return []
    segments: list[str] = []
    for part in value.split("|"):
        cleaned = part.strip().strip("«»\"'")
        if not cleaned or _PROFILE_BOILERPLATE_RE.match(cleaned):
            continue
        segments.append(cleaned)
    return segments


def _profiles_match(expected: str | None, actual: str | None) -> bool:
    if _texts_match(expected, actual):
        return True
    expected_segments = _profile_segments(expected)
    actual_segments = _profile_segments(actual)
    if not expected_segments or not actual_segments:
        return False
    for left in expected_segments:
        for right in actual_segments:
            if _texts_match(left, right):
                return True
    return False


def _discipline_names_match(expected: str | None, actual: str | None) -> bool:
    if _texts_match(expected, actual):
        return True
    for part in (actual or "").split("|"):
        if _texts_match(expected, part.strip()):
            return True
    return False


def rule_f001(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.discipline.code
    actual = ctx.fos.discipline_code
    passed = _normalize_code(expected) == _normalize_code(actual)
    return RuleResult(
        rule_id="F001",
        name="Шифр дисциплины в ФОС соответствует учебному плану",
        passed=passed,
        message="Шифры совпадают" if passed else "Шифр в ФОС не совпадает с УП",
        expected=expected,
        actual=actual,
    )


def rule_f002(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.direction_code
    actual = ctx.fos.direction_code
    if not actual:
        return RuleResult(
            rule_id="F002",
            name="Код направления в ФОС соответствует учебному плану",
            passed=False,
            message="Код направления в ФОС не найден",
            expected=expected,
        )
    passed = expected == actual
    return RuleResult(
        rule_id="F002",
        name="Код направления в ФОС соответствует учебному плану",
        passed=passed,
        message="Направления совпадают" if passed else "Код направления в ФОС и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_f003(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.profile_name
    actual = ctx.fos.profile_name
    passed = _profiles_match(expected, actual)
    return RuleResult(
        rule_id="F003",
        name="Профиль в ФОС соответствует учебному плану",
        passed=passed,
        message="Профили совпадают" if passed else "Профиль в ФОС и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_f004(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.rpd.discipline_code
    actual = ctx.fos.discipline_code
    passed = _normalize_code(expected) == _normalize_code(actual)
    return RuleResult(
        rule_id="F004",
        name="Шифр дисциплины в ФОС соответствует РПД",
        passed=passed,
        message="Шифры ФОС и РПД совпадают" if passed else "Шифры ФОС и РПД различаются",
        expected=expected,
        actual=actual,
    )


def rule_f005(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.rpd.direction_code
    actual = ctx.fos.direction_code
    if not expected or not actual:
        return RuleResult(
            rule_id="F005",
            name="Направление в ФОС соответствует РПД",
            passed=True,
            skipped=True,
            message="Недостаточно данных по направлению — проверка пропущена",
        )
    passed = expected == actual
    return RuleResult(
        rule_id="F005",
        name="Направление в ФОС соответствует РПД",
        passed=passed,
        message="Направления ФОС и РПД совпадают" if passed else "Направления ФОС и РПД различаются",
        expected=expected,
        actual=actual,
    )


def rule_f006(ctx: FosValidationContext) -> RuleResult:
    plan_codes = _plan_indicators(ctx.discipline)
    fos_codes = _fos_indicators(ctx.fos)
    if not plan_codes:
        return RuleResult(
            rule_id="F006",
            name="Компетенции УП присутствуют в ФОС",
            passed=True,
            skipped=True,
            message="В УП нет компетенций — проверка пропущена",
        )
    missing = sorted(plan_codes - fos_codes)
    passed = not missing
    return RuleResult(
        rule_id="F006",
        name="Компетенции УП присутствуют в ФОС",
        passed=passed,
        message="Все компетенции УП есть в ФОС" if passed else "Часть компетенций УП отсутствует в ФОС",
        expected="; ".join(sorted(plan_codes)),
        actual="; ".join(sorted(fos_codes)) if fos_codes else None,
    )


def rule_f007(ctx: FosValidationContext) -> RuleResult:
    fos_codes = _fos_indicators(ctx.fos)
    control_codes = {
        item.indicator_code.upper()
        for item in ctx.fos.control_items
        if item.indicator_code
    }
    if not control_codes:
        return RuleResult(
            rule_id="F007",
            name="Индикаторы таблицы контроля присутствуют в ФОС",
            passed=True,
            skipped=True,
            message="Таблица контроля без индикаторов — проверка пропущена",
        )
    missing = sorted(control_codes - fos_codes)
    passed = not missing
    return RuleResult(
        rule_id="F007",
        name="Индикаторы таблицы контроля присутствуют в ФОС",
        passed=passed,
        message="Индикаторы контроля согласованы с ФОС" if passed else "В контроле указаны индикаторы вне ФОС",
        expected="; ".join(sorted(control_codes)),
        actual="; ".join(sorted(fos_codes)),
    )


def rule_f008(ctx: FosValidationContext) -> RuleResult:
    rpd_codes = _rpd_indicators(ctx.rpd)
    control_codes = {
        item.indicator_code.upper()
        for item in ctx.fos.control_items
        if item.indicator_code
    }
    if not control_codes:
        return RuleResult(
            rule_id="F008",
            name="Индикаторы контроля ФОС присутствуют в РПД",
            passed=True,
            skipped=True,
            message="Таблица контроля без индикаторов — проверка пропущена",
        )
    if not rpd_codes:
        return RuleResult(
            rule_id="F008",
            name="Индикаторы контроля ФОС присутствуют в РПД",
            passed=False,
            message="В РПД не найдены индикаторы компетенций",
            expected="; ".join(sorted(control_codes)),
        )
    missing = sorted(control_codes - rpd_codes)
    passed = not missing
    return RuleResult(
        rule_id="F008",
        name="Индикаторы контроля ФОС присутствуют в РПД",
        passed=passed,
        message="Индикаторы контроля есть в РПД" if passed else "Индикаторы контроля отсутствуют в РПД",
        expected="; ".join(sorted(control_codes)),
        actual="; ".join(sorted(rpd_codes)),
    )


def rule_f009(ctx: FosValidationContext) -> RuleResult:
    count = len(ctx.fos.grading_criteria)
    passed = count > 0
    return RuleResult(
        rule_id="F009",
        name="В ФОС заполнена таблица критериев оценки",
        passed=passed,
        message="Критерии оценки найдены" if passed else "Таблица критериев оценки пуста",
        expected="≥1",
        actual=str(count),
    )


def rule_f010(ctx: FosValidationContext) -> RuleResult:
    topics = [item for item in ctx.fos.control_items if item.topic]
    passed = len(topics) > 0
    return RuleResult(
        rule_id="F010",
        name="В ФОС заполнена таблица контролируемых тем",
        passed=passed,
        message="Контролируемые темы найдены" if passed else "Таблица контроля пуста",
        expected="≥1",
        actual=str(len(topics)),
    )


def rule_f011(ctx: FosValidationContext) -> RuleResult:
    topics = [item for item in ctx.fos.control_items if item.topic]
    if not topics:
        return RuleResult(
            rule_id="F011",
            name="В таблице контроля указаны формы оценивания",
            passed=True,
            skipped=True,
            message="Таблица контроля пуста — проверка пропущена",
        )
    with_form = sum(1 for item in topics if item.assessment_form and item.assessment_form.strip())
    ratio = with_form / len(topics)
    passed = with_form > 0 and ratio >= 0.5
    return RuleResult(
        rule_id="F011",
        name="В таблице контроля указаны формы оценивания",
        passed=passed,
        message=(
            "Формы оценивания заполнены"
            if passed
            else "Большинство строк контроля без формы оценивания"
        ),
        expected="≥50% строк",
        actual=f"{with_form}/{len(topics)}",
    )


def rule_f012(ctx: FosValidationContext) -> RuleResult:
    criteria = ctx.fos.grading_criteria
    if not criteria:
        return RuleResult(
            rule_id="F012",
            name="В ФОС заполнена шкала баллов",
            passed=True,
            skipped=True,
            message="Таблица критериев пуста — проверка пропущена",
        )
    scaled = [
        item
        for item in criteria
        if item.grade_label and item.grade_label.strip() and item.points and item.points.strip()
    ]
    passed = len(scaled) >= 2
    return RuleResult(
        rule_id="F012",
        name="В ФОС заполнена шкала баллов",
        passed=passed,
        message="Шкала баллов заполнена" if passed else "Недостаточно строк шкалы баллов",
        expected="≥2",
        actual=str(len(scaled)),
    )


def rule_f013(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.discipline.name
    actual = ctx.fos.discipline_name
    if not actual:
        return RuleResult(
            rule_id="F013",
            name="Название дисциплины в ФОС соответствует учебному плану",
            passed=False,
            message="Название дисциплины в ФОС не найдено",
            expected=expected,
        )
    passed = _discipline_names_match(expected, actual)
    return RuleResult(
        rule_id="F013",
        name="Название дисциплины в ФОС соответствует учебному плану",
        passed=passed,
        message="Названия совпадают" if passed else "Название в ФОС и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_f014(ctx: FosValidationContext) -> RuleResult:
    expected = ctx.discipline.department_code
    actual = ctx.fos.department_code
    if not expected or not actual:
        return RuleResult(
            rule_id="F014",
            name="Код кафедры в ФОС соответствует учебному плану",
            passed=True,
            skipped=True,
            message="Код кафедры не указан в УП или ФОС — проверка пропущена",
            expected=expected,
            actual=actual,
        )
    passed = expected.strip() == actual.strip()
    return RuleResult(
        rule_id="F014",
        name="Код кафедры в ФОС соответствует учебному плану",
        passed=passed,
        message="Коды кафедры совпадают" if passed else "Код кафедры в ФОС и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_f015(ctx: FosValidationContext) -> RuleResult:
    """F015: вариант ФОС (1=дисциплина/FOSd, 2=практика/FOSp) согласован с типом дисциплины."""
    variant = ctx.fos.fos_variant
    if variant is None:
        return RuleResult(
            rule_id="F015",
            name="Вариант ФОС согласован с типом программы",
            passed=True,
            skipped=True,
            message="Вариант ФОС не определён — проверка пропущена",
        )
    from app.utils.discipline_bucket import classify_discipline_bucket

    bucket = classify_discipline_bucket(
        code=ctx.discipline.code,
        name=ctx.discipline.name,
        object_type=getattr(ctx.discipline, "object_type", None),
    )
    expected = 2 if bucket == "practices" else 1
    passed = variant == expected
    return RuleResult(
        rule_id="F015",
        name="Вариант ФОС согласован с типом программы",
        passed=passed,
        message=(
            f"Вариант {variant} соответствует типу"
            if passed
            else f"Ожидался вариант {expected} ({'FOSp' if expected == 2 else 'FOSd'}), найден {variant}"
        ),
        expected=str(expected),
        actual=str(variant),
    )


FOS_RULES: list[tuple[str, RuleFn]] = [
    ("F001", rule_f001),
    ("F002", rule_f002),
    ("F003", rule_f003),
    ("F004", rule_f004),
    ("F005", rule_f005),
    ("F006", rule_f006),
    ("F007", rule_f007),
    ("F008", rule_f008),
    ("F009", rule_f009),
    ("F010", rule_f010),
    ("F011", rule_f011),
    ("F012", rule_f012),
    ("F013", rule_f013),
    ("F014", rule_f014),
    ("F015", rule_f015),
]
