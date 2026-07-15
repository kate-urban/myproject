"""Тесты детерминированных автоправок сверки."""

from __future__ import annotations

from app.models import PlanDiscipline
from app.services.rpd_extractor import RpdExtract, VolumeBreakdown
from app.services.validation.rules import RuleResult, ValidationContext
from app.services.validation_fix import suggest_validation_fix

PASSPORT_HTML = """
<table>
<tr><td><p>Шифр и наименование дисциплины</p></td><td><p>Б1.О.99 Математика</p></td></tr>
<tr><td><p>Направление подготовки</p></td><td><p>05.03.05 Неверное</p></td></tr>
<tr><td><p>Профиль</p></td><td><p>Старый профиль</p></td></tr>
</table>
"""

VOLUME_HTML = """
<table>
<tr><td><p>Вид учебных занятий</p></td><td><p>Часов</p></td></tr>
<tr><td><p>Всего по дисциплине</p></td><td><p>200/5</p></td></tr>
<tr><td><p>Контактная работа обучающихся с преподавателем, всего</p></td><td><p>70</p></td></tr>
<tr><td><p>лекции</p></td><td><p>36</p></td></tr>
<tr><td><p>практические занятия</p></td><td><p>30</p></td></tr>
<tr><td><p>лабораторные работы</p></td><td><p>0</p></td></tr>
<tr><td><p>Самостоятельная работа</p></td><td><p>130</p></td></tr>
</table>
"""


def _ctx(**disc_kw) -> ValidationContext:
    discipline = PlanDiscipline(code="Б1.О.08", name="Математика", **disc_kw)
    rpd = RpdExtract(
        discipline_code="Б1.О.99",
        direction_code="05.03.05",
        profile_name="Старый профиль",
        discipline_name="Математика",
        hours_total=200,
        credits=5.0,
        volume=VolumeBreakdown(contact=70, lectures=36, practical=30, lab=0, sr=130),
    )
    return ValidationContext(
        direction_code="05.03.06",
        direction_name="Экология",
        profile_name="Экология и природопользование",
        discipline=discipline,
        rpd=rpd,
        plan_form="ochnaya",
    )


def test_r001_fixes_discipline_code() -> None:
    ctx = _ctx()
    rule = RuleResult(
        rule_id="R001",
        name="code",
        passed=False,
        message="fail",
        expected="Б1.О.08",
        actual="Б1.О.99",
    )
    result = suggest_validation_fix("R001", PASSPORT_HTML, ctx, rule)
    assert result.apply_safe is True
    assert result.patched_html
    assert "Б1.О.08" in result.patched_html
    assert "Б1.О.99" not in result.patched_html


def test_r002_fixes_direction_code() -> None:
    ctx = _ctx()
    rule = RuleResult(rule_id="R002", name="dir", passed=False, message="fail", expected="05.03.06", actual="05.03.05")
    result = suggest_validation_fix("R002", PASSPORT_HTML, ctx, rule)
    assert result.patched_html and "05.03.06" in result.patched_html


def test_r022_fixes_contact_hours() -> None:
    ctx = _ctx(hours_contact=72)
    rule = RuleResult(rule_id="R022", name="contact", passed=False, message="fail", expected="72", actual="70")
    result = suggest_validation_fix("R022", VOLUME_HTML, ctx, rule)
    assert result.patched_html and "72" in result.patched_html


def test_r025_adjusts_breakdown() -> None:
    ctx = _ctx()
    rule = RuleResult(rule_id="R025", name="sum", passed=False, message="fail", expected="70", actual="66")
    result = suggest_validation_fix("R025", VOLUME_HTML, ctx, rule)
    assert result.changes
    assert result.patched_html
    assert int(result.changes[0].new) > int(result.changes[0].old)
