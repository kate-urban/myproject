"""Тест мягкой проверки ЗУВ R032."""

from __future__ import annotations

from app.models import PlanDiscipline
from app.services.rpd_extractor import RpdExtract
from app.services.validation.rules import ValidationContext, rule_r032


def _ctx(*, section2: list[str], topics31: list[str]) -> ValidationContext:
    discipline = PlanDiscipline(code="Б1.О.01", name="Тест", in_plan=True)
    rpd = RpdExtract(
        discipline_code="Б1.О.01",
        section2_zuv_by_indicator={"ОПК-1.1": section2},
        topics31_zuv_phrases=topics31,
    )
    return ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=discipline,
        rpd=rpd,
    )


def test_r032_skipped_when_no_data() -> None:
    ctx = _ctx(section2=[], topics31=[])
    result = rule_r032(ctx)
    assert result.skipped
    assert result.passed


def test_r032_warns_on_paraphrase() -> None:
    base = "формировать профессиональные умения в области экологического проектирования"
    paraphrase = "формировать профессиональные навыки в области экологического проектирования"
    ctx = _ctx(section2=[base], topics31=[paraphrase])
    result = rule_r032(ctx)
    assert result.passed
    assert result.severity == "warning"
    assert "перефразирование" in result.message.lower()


def test_r032_ok_when_literal_match() -> None:
    phrase = "уметь анализировать экологические риски проекта"
    ctx = _ctx(section2=[phrase], topics31=[phrase])
    result = rule_r032(ctx)
    assert result.passed
    assert "не обнаружено" in result.message.lower()
