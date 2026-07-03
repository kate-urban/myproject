"""Правила валидации РПД против учебного плана (методичка R001–R023)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from app.models import PlanDiscipline
from app.services.rpd_extractor import INDICATOR_CODE_RE, RpdExtract

COMPETENCY_CODE_RE = re.compile(r"(?:УК|ОПК|ПК|ПСК)-\d+(?:\.\d+)?", re.IGNORECASE)


@dataclass
class ValidationContext:
    direction_code: str
    direction_name: str
    profile_name: str
    discipline: PlanDiscipline
    rpd: RpdExtract


@dataclass
class RuleResult:
    rule_id: str
    name: str
    passed: bool
    message: str
    expected: str | None = None
    actual: str | None = None
    skipped: bool = False
    severity: str = "critical"


RuleFn = Callable[[ValidationContext], RuleResult]


def _normalize_code(code: str | None) -> str:
    return (code or "").strip().upper()


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.lower().strip().strip("«»\"'")
    return re.sub(r"\s+", " ", cleaned)


def _texts_match(expected: str | None, actual: str | None) -> bool:
    left = _normalize_text(expected)
    right = _normalize_text(actual)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _plan_competencies(discipline: PlanDiscipline) -> list[str]:
    return sorted({item.competency_code.upper() for item in discipline.competencies})


def _indicator_codes(codes: list[str]) -> set[str]:
    return {code.upper() for code in codes if INDICATOR_CODE_RE.fullmatch(code.upper())}


def _competency_group(code: str) -> str | None:
    match = re.match(r"((?:УК|ОПК|ПК|ПСК)-\d+)", code.upper())
    return match.group(1) if match else None


def _rpd_contact_hours(rpd: RpdExtract) -> int | None:
    if rpd.volume.contact is not None:
        return rpd.volume.contact
    lectures = rpd.volume.lectures or 0
    practical = rpd.volume.practical or 0
    if lectures or practical:
        return lectures + practical
    return None


def _is_practice_discipline(discipline: PlanDiscipline) -> bool:
    if discipline.object_type == "3":
        return True
    code = discipline.code or ""
    return "(П)" in code.upper()


def _plan_sr_plus_control(discipline: PlanDiscipline) -> int | None:
    sr = discipline.hours_sr
    control = discipline.hours_control
    if sr is None and control is None:
        return None
    return (sr or 0) + (control or 0)


def rule_r001(ctx: ValidationContext) -> RuleResult:
    expected = ctx.discipline.code
    actual = ctx.rpd.discipline_code
    passed = _normalize_code(expected) == _normalize_code(actual)
    return RuleResult(
        rule_id="R001",
        name="Шифр дисциплины в РПД соответствует учебному плану",
        passed=passed,
        message="Шифры совпадают" if passed else "Шифр в РПД не совпадает с УП",
        expected=expected,
        actual=actual,
    )


def rule_r002(ctx: ValidationContext) -> RuleResult:
    expected = ctx.direction_code
    actual = ctx.rpd.direction_code
    if not actual:
        return RuleResult(
            rule_id="R002",
            name="Код направления в паспорте РПД соответствует учебному плану",
            passed=False,
            message="Код направления в РПД не найден",
            expected=expected,
            actual=None,
        )
    passed = expected == actual
    return RuleResult(
        rule_id="R002",
        name="Код направления в паспорте РПД соответствует учебному плану",
        passed=passed,
        message="Направления совпадают" if passed else "Код направления в РПД и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_r003(ctx: ValidationContext) -> RuleResult:
    expected = ctx.profile_name
    actual = ctx.rpd.profile_name
    passed = _texts_match(expected, actual)
    return RuleResult(
        rule_id="R003",
        name="Профиль в паспорте РПД соответствует учебному плану",
        passed=passed,
        message="Профили совпадают" if passed else "Профиль в РПД и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_r004(ctx: ValidationContext) -> RuleResult:
    expected = ctx.discipline.name
    actual = ctx.rpd.discipline_name
    passed = _texts_match(expected, actual)
    return RuleResult(
        rule_id="R004",
        name="Наименование дисциплины в РПД соответствует учебному плану",
        passed=passed,
        message="Наименования совпадают" if passed else "Наименования в РПД и УП различаются",
        expected=expected,
        actual=actual,
    )


def rule_r005(ctx: ValidationContext) -> RuleResult:
    expected = ctx.discipline.credits
    actual = ctx.rpd.credits
    if expected is None or actual is None:
        return RuleResult(
            rule_id="R005",
            name="Трудоёмкость (з.е.) в РПД соответствует учебному плану",
            passed=False,
            message="Не удалось сравнить з.е.",
            expected=str(expected) if expected is not None else None,
            actual=str(actual) if actual is not None else None,
        )
    passed = float(expected) == float(actual)
    return RuleResult(
        rule_id="R005",
        name="Трудоёмкость (з.е.) в РПД соответствует учебному плану",
        passed=passed,
        message="з.е. совпадают" if passed else "з.е. в РПД и УП различаются",
        expected=str(expected),
        actual=str(actual),
    )


def rule_r006(ctx: ValidationContext) -> RuleResult:
    expected = ctx.discipline.department_code
    actual = ctx.rpd.department_code
    if not expected:
        return RuleResult(
            rule_id="R006",
            name="Код кафедры в имени файла РПД соответствует учебному плану",
            passed=True,
            skipped=True,
            message="В УП нет кода кафедры — проверка пропущена",
            expected=None,
            actual=actual,
        )
    if not actual:
        return RuleResult(
            rule_id="R006",
            name="Код кафедры в имени файла РПД соответствует учебному плану",
            passed=False,
            message="В имени файла РПД не найден суффикс kNN",
            expected=expected,
            actual=None,
        )
    passed = str(expected) == str(actual)
    return RuleResult(
        rule_id="R006",
        name="Код кафедры в имени файла РПД соответствует учебному плану",
        passed=passed,
        message="Кафедры совпадают" if passed else "Код кафедры в РПД и УП различаются",
        expected=str(expected),
        actual=str(actual),
    )


def rule_r007(ctx: ValidationContext) -> RuleResult:
    plan_codes = _plan_competencies(ctx.discipline)
    rpd_codes = {code.upper() for code in ctx.rpd.competencies}
    if not plan_codes:
        return RuleResult(
            rule_id="R007",
            name="Компетенции УП присутствуют в разделе 2 РПД",
            passed=True,
            skipped=True,
            message="В УП нет компетенций — проверка пропущена",
        )
    if not rpd_codes:
        return RuleResult(
            rule_id="R007",
            name="Компетенции УП присутствуют в разделе 2 РПД",
            passed=False,
            message="В РПД не найдены компетенции",
            expected="; ".join(plan_codes),
            actual=None,
        )
    missing = [code for code in plan_codes if code not in rpd_codes]
    passed = not missing
    return RuleResult(
        rule_id="R007",
        name="Компетенции УП присутствуют в разделе 2 РПД",
        passed=passed,
        message="Все компетенции УП есть в РПД" if passed else "Часть компетенций УП отсутствует в РПД",
        expected="; ".join(plan_codes),
        actual="; ".join(sorted(rpd_codes)) if rpd_codes else None,
    )


def rule_r008(ctx: ValidationContext) -> RuleResult:
    """Методичка R003: директор института из справочника подписей."""
    expected = os.getenv("EXPECTED_DIRECTOR")
    actual = ctx.rpd.director_name
    if not expected:
        return RuleResult(
            rule_id="R008",
            name="Директор института соответствует справочнику подписей",
            passed=True,
            skipped=True,
            message="Справочник подписей не настроен (EXPECTED_DIRECTOR) — проверка пропущена",
            actual=actual,
        )
    if not actual:
        return RuleResult(
            rule_id="R008",
            name="Директор института соответствует справочнику подписей",
            passed=False,
            message="Блок подписей директора в РПД не найден",
            expected=expected,
        )
    passed = _texts_match(expected, actual)
    return RuleResult(
        rule_id="R008",
        name="Директор института соответствует справочнику подписей",
        passed=passed,
        message="Подпись директора совпадает" if passed else "Подпись директора не совпадает со справочником",
        expected=expected,
        actual=actual,
    )


def rule_r009(ctx: ValidationContext) -> RuleResult:
    """Методичка R002: руководитель дисциплины из справочника УП."""
    expected = os.getenv("EXPECTED_DISCIPLINE_HEAD")
    actual = ctx.rpd.discipline_head
    if not expected:
        return RuleResult(
            rule_id="R009",
            name="Руководитель дисциплины указан по справочнику УП",
            passed=True,
            skipped=True,
            message="Справочник руководителей не настроен — проверка пропущена",
            actual=actual,
        )
    if not actual:
        return RuleResult(
            rule_id="R009",
            name="Руководитель дисциплины указан по справочнику УП",
            passed=False,
            message="Руководитель дисциплины в РПД не найден",
            expected=expected,
        )
    passed = _texts_match(expected, actual)
    return RuleResult(
        rule_id="R009",
        name="Руководитель дисциплины указан по справочнику УП",
        passed=passed,
        message="Руководитель совпадает" if passed else "Руководитель дисциплины не совпадает со справочником",
        expected=expected,
        actual=actual,
    )


def rule_r010(ctx: ValidationContext) -> RuleResult:
    """Методичка R010: компетенции только из допустимых кодов ФГОС."""
    plan_codes = _plan_competencies(ctx.discipline)
    if not plan_codes:
        return RuleResult(
            rule_id="R010",
            name="Компетенции УП соответствуют кодам ФГОС",
            passed=True,
            skipped=True,
            message="В УП нет компетенций — проверка пропущена",
        )
    invalid = [code for code in plan_codes if not COMPETENCY_CODE_RE.fullmatch(code)]
    passed = not invalid
    return RuleResult(
        rule_id="R010",
        name="Компетенции УП соответствуют кодам ФГОС",
        passed=passed,
        message="Коды компетенций корректны" if passed else "Некорректные коды компетенций в УП",
        expected="; ".join(plan_codes),
        actual="; ".join(invalid) if invalid else None,
    )


def rule_r011(ctx: ValidationContext) -> RuleResult:
    """Методичка R011: список компетенций РПД полностью совпадает с УП."""
    plan_codes = set(_plan_competencies(ctx.discipline))
    rpd_indicators = _indicator_codes(ctx.rpd.competencies)
    if not plan_codes:
        return RuleResult(
            rule_id="R011",
            name="Список компетенций РПД полностью совпадает с УП",
            passed=True,
            skipped=True,
            message="В УП нет компетенций — проверка пропущена",
        )
    if not rpd_indicators:
        return RuleResult(
            rule_id="R011",
            name="Список компетенций РПД полностью совпадает с УП",
            passed=False,
            message="В РПД не найдены индикаторы компетенций",
            expected="; ".join(sorted(plan_codes)),
        )
    missing = sorted(plan_codes - rpd_indicators)
    plan_groups = {group for code in plan_codes if (group := _competency_group(code))}
    extra = sorted(
        code
        for code in rpd_indicators - plan_codes
        if (group := _competency_group(code)) and group in plan_groups
    )
    passed = not missing and not extra
    return RuleResult(
        rule_id="R011",
        name="Список компетенций РПД полностью совпадает с УП",
        passed=passed,
        message="Списки компетенций совпадают" if passed else "Списки компетенций РПД и УП различаются",
        expected="; ".join(sorted(plan_codes)),
        actual="; ".join(sorted(rpd_indicators)),
    )


def rule_r012(ctx: ValidationContext) -> RuleResult:
    """Методичка R012: уникальные комплекты ЗУВ по индикаторам."""
    texts = [re.sub(r"\s+", " ", item.strip().lower()) for item in ctx.rpd.zuv_texts if item.strip()]
    if not texts:
        return RuleResult(
            rule_id="R012",
            name="ЗУВ уникальны для каждого индикатора компетенций",
            passed=True,
            skipped=True,
            message="ЗУВ в РПД не извлечены — проверка пропущена",
        )
    duplicates = sorted({text for text in texts if texts.count(text) > 1})
    passed = not duplicates
    return RuleResult(
        rule_id="R012",
        name="ЗУВ уникальны для каждого индикатора компетенций",
        passed=passed,
        message="ЗУВ не дублируются" if passed else "Обнаружены одинаковые формулировки ЗУВ",
        actual=duplicates[0][:120] if duplicates else None,
        severity="warning",
    )


def _rule_not_in_methodology(rule_id: str, title: str) -> RuleFn:
    def _rule(_ctx: ValidationContext) -> RuleResult:
        return RuleResult(
            rule_id=rule_id,
            name=title,
            passed=True,
            skipped=True,
            message="Правило не определено в методичке R001–R023 — пропущено",
        )

    return _rule


def rule_r013(ctx: ValidationContext) -> RuleResult:
    """Согласованность таблицы 1.3: СР в объёме = сумма таблицы 3.5."""
    volume_sr = ctx.rpd.volume.sr
    sr_table = ctx.rpd.sr_table_total
    if volume_sr is None or sr_table is None:
        return RuleResult(
            rule_id="R013",
            name="СР в таблице 1.3 совпадает с итогом таблицы 3.5",
            passed=True,
            skipped=True,
            message="Недостаточно данных из таблиц 1.3/3.5 — проверка пропущена",
        )
    passed = volume_sr == sr_table
    return RuleResult(
        rule_id="R013",
        name="СР в таблице 1.3 совпадает с итогом таблицы 3.5",
        passed=passed,
        message="СР согласованы между разделами 1.3 и 3.5" if passed else "СР в 1.3 и 3.5 различаются",
        expected=str(volume_sr),
        actual=str(sr_table),
    )


def rule_r014(ctx: ValidationContext) -> RuleResult:
    """Контактная работа в 1.3 vs сумма тем раздела 3.1/3.2."""
    expected = _rpd_contact_hours(ctx.rpd)
    actual = ctx.rpd.topics_contact_hours
    if expected is None or actual is None:
        return RuleResult(
            rule_id="R014",
            name="Контактные часы в 1.3 согласованы с таблицами тем 3.1/3.2",
            passed=True,
            skipped=True,
            message="Недостаточно данных по контактным часам — проверка пропущена",
        )
    passed = expected == actual
    return RuleResult(
        rule_id="R014",
        name="Контактные часы в 1.3 согласованы с таблицами тем 3.1/3.2",
        passed=passed,
        message="Контактные часы согласованы" if passed else "Контактные часы в 1.3 и темах различаются",
        expected=str(expected),
        actual=str(actual),
    )


def rule_r020(ctx: ValidationContext) -> RuleResult:
    expected_total = ctx.discipline.hours_total
    actual_total = ctx.rpd.hours_total
    if expected_total is None or actual_total is None:
        return RuleResult(
            rule_id="R020",
            name="Объём часов в таблице 1.3 РПД соответствует учебному плану",
            passed=False,
            message="Не удалось сравнить общий объём часов",
            expected=str(expected_total) if expected_total is not None else None,
            actual=str(actual_total) if actual_total is not None else None,
        )
    if expected_total != actual_total:
        return RuleResult(
            rule_id="R020",
            name="Объём часов в таблице 1.3 РПД соответствует учебному плану",
            passed=False,
            message="Общие часы в РПД и УП различаются",
            expected=str(expected_total),
            actual=str(actual_total),
        )

    expected_sr = (
        ctx.discipline.hours_sr
        if ctx.discipline.hours_sr is not None
        else _plan_sr_plus_control(ctx.discipline)
    )
    actual_sr = ctx.rpd.volume.sr
    if expected_sr is not None and actual_sr is not None and expected_sr != actual_sr:
        return RuleResult(
            rule_id="R020",
            name="Объём часов в таблице 1.3 РПД соответствует учебному плану",
            passed=False,
            message="СР в РПД не равны СР_УП + контроль_УП",
            expected=str(expected_sr),
            actual=str(actual_sr),
        )

    return RuleResult(
        rule_id="R020",
        name="Объём часов в таблице 1.3 РПД соответствует учебному плану",
        passed=True,
        message="Часы совпадают",
        expected=str(expected_total),
        actual=str(actual_total),
    )


def rule_r021(ctx: ValidationContext) -> RuleResult:
    """Методичка R021: КР ≥ 30 ч, КП ≥ 40 ч."""
    volume = ctx.rpd.volume
    project_hours = ctx.rpd.course_project_hours or volume.course_project_hours
    work_hours = volume.course_work_hours

    if volume.has_course_project and project_hours is not None:
        passed = project_hours >= 40
        return RuleResult(
            rule_id="R021",
            name="Минимальный объём курсовой работы/проекта в РПД",
            passed=passed,
            message="Объём курсового проекта достаточен" if passed else "Курсовой проект менее 40 часов",
            expected="≥40",
            actual=str(project_hours),
        )

    if volume.has_course_work and work_hours is not None:
        passed = work_hours >= 30
        return RuleResult(
            rule_id="R021",
            name="Минимальный объём курсовой работы/проекта в РПД",
            passed=passed,
            message="Объём курсовой работы достаточен" if passed else "Курсовая работа менее 30 часов",
            expected="≥30",
            actual=str(work_hours),
        )

    return RuleResult(
        rule_id="R021",
        name="Минимальный объём курсовой работы/проекта в РПД",
        passed=True,
        skipped=True,
        message="Курсовая работа/проект в РПД не заявлены — проверка пропущена",
    )


def rule_r022(ctx: ValidationContext) -> RuleResult:
    """Методичка R022: лекции/практика в темах = учебному плану."""
    if _is_practice_discipline(ctx.discipline):
        plan_hours = ctx.discipline.hours_sr or ctx.discipline.hours_aud
        rpd_hours = ctx.rpd.volume.practical or ctx.rpd.volume.sr
        if plan_hours is not None and rpd_hours is not None:
            passed = plan_hours == rpd_hours
            return RuleResult(
                rule_id="R022",
                name="Контактные часы в РПД соответствуют учебному плану",
                passed=passed,
                message="Часы практики совпадают" if passed else "Часы практики в РПД и УП различаются",
                expected=str(plan_hours),
                actual=str(rpd_hours),
            )

    plan_contact = ctx.discipline.hours_contact or ctx.discipline.hours_aud
    rpd_contact = _rpd_contact_hours(ctx.rpd)

    if plan_contact is not None and rpd_contact is not None:
        passed = plan_contact == rpd_contact
        return RuleResult(
            rule_id="R022",
            name="Контактные часы в РПД соответствуют учебному плану",
            passed=passed,
            message="Контактные часы совпадают" if passed else "Контактные часы в РПД и УП различаются",
            expected=str(plan_contact),
            actual=str(rpd_contact),
        )

    topics_contact = ctx.rpd.topics_contact_hours
    if rpd_contact is not None and topics_contact is not None:
        passed = rpd_contact == topics_contact
        return RuleResult(
            rule_id="R022",
            name="Контактные часы в РПД соответствуют учебному плану",
            passed=passed,
            message="Контактные часы согласованы с таблицей тем" if passed else "Контактные часы в 1.3 и темах различаются",
            expected=str(rpd_contact),
            actual=str(topics_contact),
        )

    rpd_practical = ctx.rpd.volume.practical
    topics_practical = ctx.rpd.topics_practical_hours
    if rpd_practical is not None and topics_practical is not None:
        passed = rpd_practical == topics_practical
        return RuleResult(
            rule_id="R022",
            name="Контактные часы в РПД соответствуют учебному плану",
            passed=passed,
            message="Практические часы согласованы с таблицей тем" if passed else "Практические часы в 1.3 и темах различаются",
            expected=str(rpd_practical),
            actual=str(topics_practical),
        )

    return RuleResult(
        rule_id="R022",
        name="Контактные часы в РПД соответствуют учебному плану",
        passed=True,
        skipped=True,
        message="В УП нет детализации контактных часов — проверка пропущена",
    )


def rule_r023(ctx: ValidationContext) -> RuleResult:
    """Методичка R023: сумма СР в 3.5 = СР_УП + контроль_УП."""
    expected = _plan_sr_plus_control(ctx.discipline)
    actual = ctx.rpd.sr_table_total or ctx.rpd.volume.sr

    if expected is None or actual is None:
        if ctx.rpd.sr_table_total is not None and ctx.rpd.volume.sr is not None:
            passed = ctx.rpd.sr_table_total == ctx.rpd.volume.sr
            return RuleResult(
                rule_id="R023",
                name="Таблица 3.5: сумма СР согласована с разделом 1.3",
                passed=passed,
                message="СР в 3.5 и 1.3 согласованы" if passed else "СР в 3.5 и 1.3 различаются",
                expected=str(ctx.rpd.volume.sr),
                actual=str(ctx.rpd.sr_table_total),
            )
        return RuleResult(
            rule_id="R023",
            name="Таблица 3.5: сумма СР согласована с учебным планом",
            passed=True,
            skipped=True,
            message="Недостаточно данных по СР — проверка пропущена",
        )

    passed = expected == actual
    return RuleResult(
        rule_id="R023",
        name="Таблица 3.5: сумма СР согласована с учебным планом",
        passed=passed,
        message="СР согласованы с УП" if passed else "Сумма СР в 3.5 не равна СР_УП + контроль_УП",
        expected=str(expected),
        actual=str(actual),
    )


RULES: list[tuple[str, RuleFn]] = [
    ("R001", rule_r001),
    ("R002", rule_r002),
    ("R003", rule_r003),
    ("R004", rule_r004),
    ("R005", rule_r005),
    ("R006", rule_r006),
    ("R007", rule_r007),
    ("R008", rule_r008),
    ("R009", rule_r009),
    ("R010", rule_r010),
    ("R011", rule_r011),
    ("R012", rule_r012),
    ("R013", rule_r013),
    ("R014", rule_r014),
    ("R015", _rule_not_in_methodology("R015", "Правило R015")),
    ("R016", _rule_not_in_methodology("R016", "Правило R016")),
    ("R017", _rule_not_in_methodology("R017", "Правило R017")),
    ("R018", _rule_not_in_methodology("R018", "Правило R018")),
    ("R019", _rule_not_in_methodology("R019", "Правило R019")),
    ("R020", rule_r020),
    ("R021", rule_r021),
    ("R022", rule_r022),
    ("R023", rule_r023),
]

DEFAULT_RULE_IDS = [
    "R001",
    "R002",
    "R003",
    "R004",
    "R005",
    "R006",
    "R007",
    "R008",
    "R009",
    "R010",
    "R011",
    "R012",
    "R013",
    "R014",
    "R020",
    "R021",
    "R022",
    "R023",
]
