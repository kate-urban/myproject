"""Пропуск сверки, если в таблице 1.3 указано «не предусмотрено учебным планом»."""

from __future__ import annotations

from app.models import PlanDiscipline, StudyPlan
from app.services.rpd_extractor import RpdExtract, VolumeBreakdown, _is_not_in_plan_text
from app.services.validation.rules import rule_r022, ValidationContext, _rpd_contact_hours


def test_is_not_in_plan_text() -> None:
    assert _is_not_in_plan_text("Не предусмотрены учебным планом")
    assert _is_not_in_plan_text("не предусмотрено планом обучения")
    assert not _is_not_in_plan_text("36")
    assert not _is_not_in_plan_text("-")


def test_r022_skips_when_contact_not_in_plan() -> None:
    plan = StudyPlan(source_file="test.plx", source_format="xml_upvo", form="ochnaya")
    discipline = PlanDiscipline(
        code="Б1.В.01",
        name="Тест",
        hours_contact=36,
        hours_aud=36,
        in_plan=True,
    )
    rpd = RpdExtract(
        discipline_code="Б1.В.01",
        volume=VolumeBreakdown(contact_not_in_plan=True, practical=36),
    )
    ctx = ValidationContext(
        direction_code="05.03.06",
        direction_name="Экология",
        profile_name="Профиль",
        discipline=discipline,
        rpd=rpd,
    )
    result = rule_r022(ctx)
    assert result.skipped is True
    assert result.passed is True
    assert "не предусмотрен" in result.message.lower()


def test_rpd_contact_hours_none_lectures_plus_practical() -> None:
    rpd = RpdExtract(
        volume=VolumeBreakdown(
            contact=None,
            lectures=None,
            lectures_not_in_plan=True,
            practical=36,
        ),
    )
    assert _rpd_contact_hours(rpd) == 36


def test_r022_passes_when_only_practical_in_plan() -> None:
    plan = StudyPlan(source_file="test.plx", source_format="xml_upvo", form="ochnaya")
    discipline = PlanDiscipline(
        code="Б1.В.01",
        name="Тест",
        hours_contact=36,
        hours_aud=36,
        in_plan=True,
    )
    rpd = RpdExtract(
        discipline_code="Б1.В.01",
        volume=VolumeBreakdown(
            contact=108,
            lectures_not_in_plan=True,
            lectures=None,
            practical=36,
        ),
    )
    ctx = ValidationContext(
        direction_code="05.03.06",
        direction_name="Экология",
        profile_name="Профиль",
        discipline=discipline,
        rpd=rpd,
    )
    result = rule_r022(ctx)
    assert result.passed is True
    assert not result.skipped
