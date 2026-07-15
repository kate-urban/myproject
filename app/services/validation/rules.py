"""Правила валидации РПД против учебного плана (методичка R001–R023)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from app.models import PlanDiscipline
from app.services.rpd_extractor import INDICATOR_CODE_RE, RpdExtract, normalize_competency_code

COMPETENCY_CODE_RE = re.compile(r"(?:УК|ОПК|ПК|ПСК)-\d+(?:\.\d+)?", re.IGNORECASE)


@dataclass
class ValidationContext:
    direction_code: str
    direction_name: str
    profile_name: str
    discipline: PlanDiscipline
    rpd: RpdExtract
    plan_form: str | None = None


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
    return sorted(
        {normalize_competency_code(item.competency_code) for item in discipline.competencies}
    )


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


def _normalize_zuv_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_extramural_form(form: str | None) -> bool:
    if not form:
        return False
    lowered = form.lower()
    return any(token in lowered for token in ("zaoch", "заоч", "oz", "очно-заоч"))


def _section2_phrases_for_plan(ctx: ValidationContext) -> set[str]:
    plan_indicators = _indicator_codes(_plan_competencies(ctx.discipline))
    phrases: set[str] = set()
    by_ind = ctx.rpd.section2_zuv_by_indicator
    if not by_ind:
        return phrases
    for code, items in by_ind.items():
        if code == "_ungrouped":
            phrases.update(items)
            continue
        if not plan_indicators or code in plan_indicators:
            phrases.update(items)
    return phrases


def _zuv_hint_text(ctx: ValidationContext, missing: str) -> str | None:
    for code, items in ctx.rpd.section2_zuv_by_indicator.items():
        for item in items:
            if missing in item or item in missing:
                return f"Скопируйте из п.2 ({code}): …{item[:100]}…"
    return None


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


def _rpd_competency_codes(rpd: RpdExtract) -> set[str]:
    """Коды компетенций РПД: таблица 2.1 + индикаторы из колонки «Индикаторы…» / п.2."""
    codes = {normalize_competency_code(code) for code in rpd.competencies}
    for key in rpd.section2_zuv_by_indicator:
        if key != "_ungrouped":
            codes.add(normalize_competency_code(key))
    return codes


def rule_r007(ctx: ValidationContext) -> RuleResult:
    plan_codes = _plan_competencies(ctx.discipline)
    rpd_codes = _rpd_competency_codes(ctx.rpd)
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
    indicator_actual = sorted(_indicator_codes(list(rpd_codes)))
    display_actual = indicator_actual or sorted(rpd_codes)
    return RuleResult(
        rule_id="R007",
        name="Компетенции УП присутствуют в разделе 2 РПД",
        passed=passed,
        message="Все компетенции УП есть в РПД" if passed else "Часть компетенций УП отсутствует в РПД",
        expected="; ".join(plan_codes),
        actual="; ".join(display_actual) if display_actual else None,
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
    rpd_indicators = _indicator_codes(list(_rpd_competency_codes(ctx.rpd)))
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


def rule_r015(ctx: ValidationContext) -> RuleResult:
    """ТЗ блок А: З/У/В в таблице 3.1 буквально копируют формулировки из п.2."""
    section2 = _section2_phrases_for_plan(ctx)
    topics31 = {_normalize_zuv_phrase(p) for p in ctx.rpd.topics31_zuv_phrases if p.strip()}

    if not section2 and not topics31:
        return RuleResult(
            rule_id="R015",
            name="З/У/В в таблице 3.1 совпадают с разделом 2 (exact match)",
            passed=True,
            skipped=True,
            message="З/У/В не извлечены — проверка пропущена",
        )
    if not section2:
        return RuleResult(
            rule_id="R015",
            name="З/У/В в таблице 3.1 совпадают с разделом 2 (exact match)",
            passed=True,
            skipped=True,
            message="З/У/В раздела 2 не извлечены — проверка пропущена",
        )
    if not topics31:
        return RuleResult(
            rule_id="R015",
            name="З/У/В в таблице 3.1 совпадают с разделом 2 (exact match)",
            passed=False,
            message="В таблице 3.1 не найдены формулировки З/У/В",
            expected=f"{len(section2)} формулировок из п.2",
        )

    extra_in_31 = sorted(topics31 - section2)
    missing_in_31 = sorted(section2 - topics31)

    if extra_in_31:
        hint = _zuv_hint_text(ctx, extra_in_31[0])
        return RuleResult(
            rule_id="R015",
            name="З/У/В в таблице 3.1 совпадают с разделом 2 (exact match)",
            passed=False,
            message="В 3.1 есть перефразирование или лишние формулировки (не из п.2)"
            + (f". {hint}" if hint else ""),
            expected=extra_in_31[0][:120],
            actual="не найдено в п.2",
        )

    if missing_in_31:
        return RuleResult(
            rule_id="R015",
            name="З/У/В в таблице 3.1 совпадают с разделом 2 (exact match)",
            passed=False,
            message="В 3.1 пропущены формулировки из п.2 — скопируйте текст буквально",
            expected=missing_in_31[0][:120],
            actual=f"отсутствует в 3.1 ({len(missing_in_31)} шт.)",
        )

    return RuleResult(
        rule_id="R015",
        name="З/У/В в таблице 3.1 совпадают с разделом 2 (exact match)",
        passed=True,
        message="Все формулировки 3.1 совпадают с разделом 2",
    )


def rule_r016(ctx: ValidationContext) -> RuleResult:
    """ТЗ блок В: обязательные строки 3.5, часы контроля = план, минимумы."""
    rpd = ctx.rpd
    if rpd.sr_table_total is None and not rpd.sr_rows:
        return RuleResult(
            rule_id="R016",
            name="Таблица 3.5: обязательные виды СР и часы контроля",
            passed=True,
            skipped=True,
            message="Таблица 3.5 не извлечена — проверка пропущена",
        )

    issues: list[str] = []

    if not rpd.sr_has_current_control:
        issues.append("нет строки «Подготовка к текущему контролю»")

    if _is_extramural_form(ctx.plan_form) and not rpd.sr_has_homework_control:
        issues.append("для заочной формы нет «Подготовки к домашним контрольным работам»")

    plan_control = ctx.discipline.hours_control
    rpd_control = rpd.sr_control_work_hours

    if plan_control is None:
        pass
    elif plan_control == 0:
        if rpd_control is not None and rpd_control > 0:
            issues.append(f"в плане нет контроля, в 3.5 указано {rpd_control} ч (нужен прочерк)")
    elif rpd_control is not None and rpd_control != plan_control:
        issues.append(f"часы контрольной в 3.5 ({rpd_control}) ≠ плану ({plan_control})")
    elif rpd_control is not None and 0 < rpd_control < 10:
        issues.append(f"контрольная работа {rpd_control} ч < минимума 10 ч")

    kr_h = rpd.sr_course_work_hours_35
    if kr_h is not None and kr_h > 0 and kr_h < 30:
        issues.append(f"курсовая работа в 3.5: {kr_h} ч < 30 ч")
    kp_h = rpd.sr_course_project_hours_35
    if kp_h is not None and kp_h > 0 and kp_h < 40:
        issues.append(f"курсовой проект в 3.5: {kp_h} ч < 40 ч")

    passed = not issues
    return RuleResult(
        rule_id="R016",
        name="Таблица 3.5: обязательные виды СР и часы контроля",
        passed=passed,
        message="Таблица 3.5 соответствует требованиям" if passed else "; ".join(issues),
        expected=str(plan_control) if plan_control else "прочерк",
        actual=str(rpd_control) if rpd_control is not None else None,
    )


def rule_r017(ctx: ValidationContext) -> RuleResult:
    """ТЗ блок Б: в матрице 3.1 КР/КП/контрольные — только +/-, без часов."""
    if not ctx.rpd.topics31_has_flag_columns:
        return RuleResult(
            rule_id="R017",
            name="Таблица 3.1: КР/КП/контрольные отмечены +/- (без часов)",
            passed=True,
            skipped=True,
            message="Колонки КР/КП в таблице 3.1 не найдены — проверка пропущена",
        )
    violations = ctx.rpd.topics31_flag_hour_violations
    if violations:
        return RuleResult(
            rule_id="R017",
            name="Таблица 3.1: КР/КП/контрольные отмечены +/- (без часов)",
            passed=False,
            message="В таблице 3.1 указаны часы вместо +/- для КР/КП/контрольных",
            actual=violations[0][:120],
        )
    return RuleResult(
        rule_id="R017",
        name="Таблица 3.1: КР/КП/контрольные отмечены +/- (без часов)",
        passed=True,
        message="КР/КП/контрольные отмечены корректно (+/-, без часов)",
    )


def rule_r018(ctx: ValidationContext) -> RuleResult:
    """ТЗ блок Г: нумерация X.Y вопросов и сумма часов детализации = итог 3.5."""
    questions = ctx.rpd.sr_questions
    if not questions:
        return RuleResult(
            rule_id="R018",
            name="Детализация СР: нумерация X.Y и сумма часов",
            passed=True,
            skipped=True,
            message="Таблица вопросов для самостоятельного изучения не найдена — пропущено",
        )

    topic_set = set(ctx.rpd.topic_numbers)
    bad_nums: list[str] = []
    for q in questions:
        topic = q.get("topic")
        number = q.get("number", "")
        if topic_set and topic not in topic_set:
            bad_nums.append(number)

    q_total = ctx.rpd.sr_questions_hours_total
    budget = ctx.rpd.sr_self_study_budget_hours
    sr_total = ctx.rpd.sr_table_total
    compare_to = budget if budget is not None else sr_total

    if bad_nums:
        return RuleResult(
            rule_id="R018",
            name="Детализация СР: нумерация X.Y и сумма часов",
            passed=False,
            message=f"Вопросы {', '.join(bad_nums[:5])} не привязаны к темам из 3.1",
            expected=f"темы: {sorted(topic_set)[:10]}",
            actual=bad_nums[0],
        )

    if q_total is not None and compare_to is not None and q_total != compare_to:
        return RuleResult(
            rule_id="R018",
            name="Детализация СР: нумерация X.Y и сумма часов",
            passed=False,
            message="Сумма часов по вопросам ≠ итогу детализации в 3.5",
            expected=str(compare_to),
            actual=str(q_total),
        )

    if q_total is not None and compare_to is None:
        return RuleResult(
            rule_id="R018",
            name="Детализация СР: нумерация X.Y и сумма часов",
            passed=True,
            message="Нумерация X.Y корректна; итог 3.5 для сверки суммы не найден",
        )

    return RuleResult(
        rule_id="R018",
        name="Детализация СР: нумерация X.Y и сумма часов",
        passed=True,
        message="Нумерация и сумма часов детализации согласованы",
        expected=str(compare_to) if compare_to is not None else None,
        actual=str(q_total) if q_total is not None else None,
    )


def rule_r019(ctx: ValidationContext) -> RuleResult:
    """ТЗ блок Г: матрица 3.6 — суммы, темы, СР ≥ вопросы по теме."""
    matrix = ctx.rpd.matrix_36_rows
    if not matrix:
        return RuleResult(
            rule_id="R019",
            name="Матрица 3.6: суммы часов и СР ≥ вопросы по теме",
            passed=True,
            skipped=True,
            message="Матрица 3.6 не извлечена — проверка пропущена",
        )

    topic_set = set(ctx.rpd.topic_numbers)
    matrix_topics = {row["topic"] for row in matrix if row.get("topic") is not None}

    if topic_set:
        missing = sorted(topic_set - matrix_topics)
        extra = sorted(matrix_topics - topic_set)
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"нет тем {missing[:5]}")
            if extra:
                detail.append(f"лишние темы {extra[:5]}")
            return RuleResult(
                rule_id="R019",
                name="Матрица 3.6: суммы часов и СР ≥ вопросы по теме",
                passed=False,
                message="Темы матрицы 3.6 не совпадают с таблицей 3.1: " + "; ".join(detail),
            )

    col_sums = {"lec": 0, "prac": 0, "lab": 0, "sr": 0, "total": 0}
    col_present = {k: False for k in col_sums}
    for row in matrix:
        for key in col_sums:
            val = row.get(key)
            if val is not None:
                col_sums[key] += val
                col_present[key] = True

    totals = ctx.rpd.matrix_36_col_totals
    if totals:
        for key in ("lec", "prac", "lab", "sr", "total"):
            if not col_present.get(key):
                continue
            expected = totals.get(key)
            if expected is not None and col_sums[key] != expected:
                return RuleResult(
                    rule_id="R019",
                    name="Матрица 3.6: суммы часов и СР ≥ вопросы по теме",
                    passed=False,
                    message=f"Сумма по столбцу «{key}» ({col_sums[key]}) ≠ итогу ({expected})",
                    expected=str(expected),
                    actual=str(col_sums[key]),
                )

    question_hours_by_topic: dict[int, int] = {}
    for q in ctx.rpd.sr_questions:
        topic = q.get("topic")
        hours = q.get("hours")
        if topic is not None and hours is not None:
            question_hours_by_topic[topic] = question_hours_by_topic.get(topic, 0) + hours

    for row in matrix:
        topic = row.get("topic")
        sr_hours = row.get("sr")
        if topic is None or sr_hours is None:
            continue
        q_hours = question_hours_by_topic.get(topic, 0)
        if q_hours > 0 and sr_hours < q_hours:
            return RuleResult(
                rule_id="R019",
                name="Матрица 3.6: суммы часов и СР ≥ вопросы по теме",
                passed=False,
                message=f"Тема {topic}: СР в 3.6 ({sr_hours} ч) < суммы вопросов ({q_hours} ч)",
                expected=f"≥{q_hours}",
                actual=str(sr_hours),
            )

    for row in matrix:
        parts = [row.get(k) for k in ("lec", "prac", "lab", "sr")]
        nums = [p for p in parts if p is not None]
        total = row.get("total")
        if nums and total is not None and sum(nums) != total:
            return RuleResult(
                rule_id="R019",
                name="Матрица 3.6: суммы часов и СР ≥ вопросы по теме",
                passed=False,
                message=f"Тема {row.get('topic')}: сумма по строке ({sum(nums)}) ≠ итогу ({total})",
                expected=str(total),
                actual=str(sum(nums)),
            )

    return RuleResult(
        rule_id="R019",
        name="Матрица 3.6: суммы часов и СР ≥ вопросы по теме",
        passed=True,
        message="Матрица 3.6 согласована с темами и вопросами",
    )


def rule_r024(ctx: ValidationContext) -> RuleResult:
    """ТЗ: профессиональные компетенции (ПК) всегда имеют группы."""
    if ctx.rpd.pk_groups_ok is None:
        return RuleResult(
            rule_id="R024",
            name="ПК в разделе 2 имеют группы (внутренние группы вуза)",
            passed=True,
            skipped=True,
            message="ПК в РПД не найдены — проверка пропущена",
        )
    passed = ctx.rpd.pk_groups_ok
    return RuleResult(
        rule_id="R024",
        name="ПК в разделе 2 имеют группы (внутренние группы вуза)",
        passed=passed,
        message="Все ПК сгруппированы" if passed else "Есть ПК без группы в таблице 2.1",
        actual="; ".join(ctx.rpd.pk_indicators_without_group[:5]) if not passed else None,
    )


def rule_r025(ctx: ValidationContext) -> RuleResult:
    """ТЗ: лекции + практики + лабораторные = контакт в 1.3."""
    vol = ctx.rpd.volume
    parts = [vol.lectures, vol.practical, vol.lab]
    if all(p is None for p in parts):
        return RuleResult(
            rule_id="R025",
            name="Лекции + практики + лабораторные = контакт в 1.3",
            passed=True,
            skipped=True,
            message="Детализация лек/практ/лаб в 1.3 не найдена — пропущено",
        )
    contact = _rpd_contact_hours(ctx.rpd)
    if contact is None:
        return RuleResult(
            rule_id="R025",
            name="Лекции + практики + лабораторные = контакт в 1.3",
            passed=True,
            skipped=True,
            message="Контактные часы в 1.3 не найдены — пропущено",
        )
    breakdown_sum = (vol.lectures or 0) + (vol.practical or 0) + (vol.lab or 0)
    passed = breakdown_sum == contact
    return RuleResult(
        rule_id="R025",
        name="Лекции + практики + лабораторные = контакт в 1.3",
        passed=passed,
        message="Разбивка контакта согласована" if passed else "Лек+практ+лаб ≠ контакт в 1.3",
        expected=str(contact),
        actual=str(breakdown_sum),
    )


def rule_r026(ctx: ValidationContext) -> RuleResult:
    """ТЗ: сумма лек/практ/лаб по темам 3.1/3.2 = контакт по плану (дневная форма)."""
    rpd_lec = ctx.rpd.topics_lecture_hours or ctx.rpd.volume.lectures
    rpd_prac = ctx.rpd.topics_practical_hours or ctx.rpd.volume.practical
    rpd_lab = ctx.rpd.volume.lab

    if rpd_lec is None and rpd_prac is None and rpd_lab is None:
        return RuleResult(
            rule_id="R026",
            name="Сумма лек/практ/лаб по темам согласована с 1.3",
            passed=True,
            skipped=True,
            message="Часы по видам занятий в темах не извлечены — пропущено",
        )

    topics_sum = (rpd_lec or 0) + (rpd_prac or 0) + (rpd_lab or 0)
    contact_13 = _rpd_contact_hours(ctx.rpd)
    if contact_13 is not None and topics_sum != contact_13:
        return RuleResult(
            rule_id="R026",
            name="Сумма лек/практ/лаб по темам согласована с 1.3",
            passed=False,
            message="Сумма лек+практ+лаб по темам ≠ контакту в 1.3",
            expected=str(contact_13),
            actual=str(topics_sum),
        )

    plan_contact = ctx.discipline.hours_contact or ctx.discipline.hours_aud
    if plan_contact is not None and topics_sum != plan_contact:
        return RuleResult(
            rule_id="R026",
            name="Сумма лек/практ/лаб по темам согласована с 1.3",
            passed=False,
            message="Сумма лек+практ+лаб по темам ≠ контактным часам УП",
            expected=str(plan_contact),
            actual=str(topics_sum),
        )

    return RuleResult(
        rule_id="R026",
        name="Сумма лек/практ/лаб по темам согласована с 1.3",
        passed=True,
        message="Суммы по видам занятий согласованы",
        expected=str(plan_contact or contact_13),
        actual=str(topics_sum),
    )


def rule_r027(ctx: ValidationContext) -> RuleResult:
    """ТЗ: детализация 3.5 — сумма строк (кроме итога) согласована с итогом."""
    rows = ctx.rpd.sr_rows
    total = ctx.rpd.sr_table_total
    if not rows or total is None:
        return RuleResult(
            rule_id="R027",
            name="Сумма строк таблицы 3.5 = итог СР",
            passed=True,
            skipped=True,
            message="Строки таблицы 3.5 не извлечены — пропущено",
        )
    row_sum = sum(r["hours"] for r in rows if r.get("hours") is not None)
    if row_sum != total:
        return RuleResult(
            rule_id="R027",
            name="Сумма строк таблицы 3.5 = итог СР",
            passed=False,
            message="Сумма по видам СР ≠ итоговой строке 3.5",
            expected=str(total),
            actual=str(row_sum),
        )
    return RuleResult(
        rule_id="R027",
        name="Сумма строк таблицы 3.5 = итог СР",
        passed=True,
        message="Сумма строк 3.5 согласована с итогом",
        expected=str(total),
        actual=str(row_sum),
    )


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


def _assessment_tuple(form_type: str, semester: int | None) -> tuple[str, int]:
    return (form_type, semester or 0)


def _plan_assessments(ctx: ValidationContext) -> set[tuple[str, int]]:
    items = getattr(ctx.discipline, "assessments", None) or []
    return {_assessment_tuple(a.form_type, a.semester) for a in items}


def _rpd_assessments(ctx: ValidationContext) -> set[tuple[str, int]]:
    result: set[tuple[str, int]] = set()
    for item in ctx.rpd.topics31_assessments:
        result.add(_assessment_tuple(item.get("form_type", ""), item.get("semester")))
    return {x for x in result if x[0]}


def rule_r028(ctx: ValidationContext) -> RuleResult:
    """ТЗ блок Б: формы аттестации в 3.1 по семестрам = учебному плану."""
    plan_set = _plan_assessments(ctx)
    rpd_set = _rpd_assessments(ctx)
    if not plan_set and not rpd_set:
        return RuleResult(
            rule_id="R028",
            name="Формы аттестации в 3.1 соответствуют учебному плану",
            passed=True,
            skipped=True,
            message="Формы аттестации не извлечены — проверка пропущена",
        )
    if not plan_set:
        return RuleResult(
            rule_id="R028",
            name="Формы аттестации в 3.1 соответствуют учебному плану",
            passed=True,
            skipped=True,
            message="В УП нет форм аттестации — проверка пропущена",
        )
    if not rpd_set:
        return RuleResult(
            rule_id="R028",
            name="Формы аттестации в 3.1 соответствуют учебному плану",
            passed=False,
            message="В таблице 3.1 не найдены формы аттестации по семестрам",
            expected=_format_assessment_set(plan_set),
        )
    missing = sorted(plan_set - rpd_set)
    extra = sorted(rpd_set - plan_set)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"нет в РПД: {_format_assessment_set(missing)}")
        if extra:
            parts.append(f"лишние в РПД: {_format_assessment_set(extra)}")
        return RuleResult(
            rule_id="R028",
            name="Формы аттестации в 3.1 соответствуют учебному плану",
            passed=False,
            message="; ".join(parts),
            expected=_format_assessment_set(plan_set),
            actual=_format_assessment_set(rpd_set),
        )
    return RuleResult(
        rule_id="R028",
        name="Формы аттестации в 3.1 соответствуют учебному плану",
        passed=True,
        message="Формы аттестации и семестры совпадают с УП",
    )


def _format_assessment_set(items: set[tuple[str, int]] | list[tuple[str, int]]) -> str:
    labels = {
        "exam": "экзамен",
        "zachet": "зачёт",
        "zachet_graded": "зачёт с оц.",
        "kp": "КП",
        "kr": "КР",
        "control_work": "контрольная",
    }
    parts = []
    for form_type, semester in sorted(items):
        name = labels.get(form_type, form_type)
        parts.append(f"{name} (сем.{semester})" if semester else name)
    return "; ".join(parts)


def rule_r029(ctx: ValidationContext) -> RuleResult:
    """ТЗ: названия тем в 3.1/3.2 выделены жирным (заголовок vs детализация)."""
    topics = ctx.rpd.topic_numbers
    bold = ctx.rpd.topic_titles_bold
    if not topics:
        return RuleResult(
            rule_id="R029",
            name="Названия тем выделены жирным шрифтом",
            passed=True,
            skipped=True,
            message="Темы не извлечены — проверка пропущена",
        )
    bold_nums = {item.get("topic") for item in bold if item.get("topic") is not None}
    missing = sorted(set(topics) - bold_nums)
    if missing:
        return RuleResult(
            rule_id="R029",
            name="Названия тем выделены жирным шрифтом",
            passed=False,
            message=f"Темы без жирного заголовка: {missing[:8]}",
            expected=f"жирный заголовок для тем {sorted(topics)[:10]}",
            actual=f"жирно: {sorted(bold_nums)[:10]}",
            severity="warning",
        )
    return RuleResult(
        rule_id="R029",
        name="Названия тем выделены жирным шрифтом",
        passed=True,
        message="Заголовки тем оформлены жирным",
    )


def rule_r030(ctx: ValidationContext) -> RuleResult:
    """ТЗ: лист «Сведения о переутверждении» заполнен (есть годы)."""
    if not ctx.rpd.has_reapproval_section:
        return RuleResult(
            rule_id="R030",
            name="Лист переутверждения заполнен",
            passed=True,
            skipped=True,
            message="Раздел переутверждения не найден — проверка пропущена",
        )
    if ctx.rpd.reapproval_years:
        return RuleResult(
            rule_id="R030",
            name="Лист переутверждения заполнен",
            passed=True,
            message=f"Указаны годы переутверждения: {ctx.rpd.reapproval_years}",
        )
    return RuleResult(
        rule_id="R030",
        name="Лист переутверждения заполнен",
        passed=False,
        message="Раздел «Сведения о переутверждении» есть, но годы не заполнены",
        expected="год(ы) переутверждения в таблице",
        actual="пусто",
        severity="warning",
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
    ("R015", rule_r015),
    ("R016", rule_r016),
    ("R017", rule_r017),
    ("R018", rule_r018),
    ("R019", rule_r019),
    ("R020", rule_r020),
    ("R021", rule_r021),
    ("R022", rule_r022),
    ("R023", rule_r023),
    ("R024", rule_r024),
    ("R025", rule_r025),
    ("R026", rule_r026),
    ("R027", rule_r027),
    ("R028", rule_r028),
    ("R029", rule_r029),
    ("R030", rule_r030),
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
    "R015",
    "R016",
    "R017",
    "R018",
    "R019",
    "R020",
    "R021",
    "R022",
    "R023",
    "R024",
    "R025",
    "R026",
    "R027",
    "R028",
    "R029",
    "R030",
]

# Базовые правила MVP (golden-тесты, обратная совместимость)
CORE_RULE_IDS = [
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
