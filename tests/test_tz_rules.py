"""Тесты правил ТЗ R015–R019, R024–R027."""

from __future__ import annotations

from types import SimpleNamespace

from app.models import PlanDiscipline
from app.services.rpd_extractor import RpdExtract, VolumeBreakdown
from app.services.validation.rules import (
    ValidationContext,
    rule_r015,
    rule_r016,
    rule_r017,
    rule_r018,
    rule_r019,
    rule_r024,
    rule_r025,
    rule_r027,
    rule_r028,
    rule_r029,
)


def _ctx(rpd: RpdExtract, **disc_kw) -> ValidationContext:
    discipline = PlanDiscipline(code="Б1.О.01.07", name="Тест", **disc_kw)
    return ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=discipline,
        rpd=rpd,
        plan_form="ochnaya",
    )


def test_r015_passes_on_exact_zuv_match() -> None:
    rpd = RpdExtract(
        section2_zuv_by_indicator={"ОПК-3.1": ["законы физики", "методы расчёта"]},
        topics31_zuv_phrases=["законы физики", "методы расчёта"],
    )
    result = rule_r015(_ctx(rpd))
    assert result.passed is True


def test_r015_fails_on_paraphrase() -> None:
    rpd = RpdExtract(
        section2_zuv_by_indicator={"ОПК-3.1": ["знать законы физики"]},
        topics31_zuv_phrases=["знать базовую механику"],
    )
    result = rule_r015(_ctx(rpd))
    assert result.passed is False


def test_r015_passes_with_punctuation_diff() -> None:
    rpd = RpdExtract(
        section2_zuv_by_indicator={"ОПК-1.1": ["знать законы физики;"]},
        topics31_zuv_phrases=["знать законы физики"],
    )
    result = rule_r015(_ctx(rpd))
    assert result.passed is True


def test_r015_passes_when_topics31_expand_section2() -> None:
    rpd = RpdExtract(
        section2_zuv_by_indicator={
            "ОПК-1.1": ["знать основные понятия и утверждения изучаемых разделов математики"]
        },
        topics31_zuv_phrases=[
            "знать основные понятия и утверждения линейной алгебры изучаемых разделов"
        ],
    )
    result = rule_r015(_ctx(rpd))
    assert result.passed is True


def test_r015_passes_without_trailing_competency_codes() -> None:
    rpd = RpdExtract(
        section2_zuv_by_indicator={"УК-5.2": ["уметь находить и использовать социальную информацию"]},
        topics31_zuv_phrases=["уметь находить и использовать социальную информацию ук-5 2"],
    )
    result = rule_r015(_ctx(rpd))
    assert result.passed is True


def test_r016_requires_current_control_row() -> None:
    rpd = RpdExtract(sr_table_total=100, sr_has_current_control=False)
    result = rule_r016(_ctx(rpd))
    assert result.passed is False
    assert "текущему контролю" in result.message


def test_r016_fails_when_control_hours_missing_in_35() -> None:
    rpd = RpdExtract(sr_table_total=100, sr_has_current_control=True, sr_control_work_hours=None)
    result = rule_r016(_ctx(rpd, hours_control=10))
    assert result.passed is False
    assert "не указаны часы контрольной" in result.message


def test_r026_uses_topics_lab_hours() -> None:
    from app.services.validation.rules import rule_r026

    rpd = RpdExtract(
        volume=VolumeBreakdown(contact=100, lectures=40, practical=50, lab=10),
        topics_lecture_hours=40,
        topics_practical_hours=50,
        topics_lab_hours=10,
    )
    result = rule_r026(_ctx(rpd, hours_contact=100))
    assert result.passed is True


def test_r026_fails_when_lab_missing_from_topics() -> None:
    from app.services.validation.rules import rule_r026

    rpd = RpdExtract(
        volume=VolumeBreakdown(contact=100, lectures=40, practical=50, lab=10),
        topics_lecture_hours=40,
        topics_practical_hours=50,
        topics_lab_hours=None,
    )
    result = rule_r026(_ctx(rpd, hours_contact=100))
    assert result.passed is False


def test_r016_control_hours_must_match_plan() -> None:
    rpd = RpdExtract(
        sr_table_total=100,
        sr_has_current_control=True,
        sr_control_work_hours=7,
    )
    result = rule_r016(_ctx(rpd, hours_control=10))
    assert result.passed is False


def test_r017_fails_on_numeric_kp_flag() -> None:
    rpd = RpdExtract(
        topics31_has_flag_columns=True,
        topics31_flag_hour_violations=["тема 1: kp='30'"],
    )
    result = rule_r017(_ctx(rpd))
    assert result.passed is False


def test_r018_skips_hour_total_without_budget_row() -> None:
    rpd = RpdExtract(
        topic_numbers=[1, 2],
        sr_questions=[{"number": "1.1", "topic": 1, "hours": 10}],
        sr_questions_hours_total=10,
        sr_table_total=144,
        sr_self_study_budget_hours=None,
    )
    result = rule_r018(_ctx(rpd))
    assert result.passed is True
    assert "итог 3.5" in result.message.lower() or "сверки" in result.message.lower()


def test_r018_bad_question_topic_number() -> None:
    rpd = RpdExtract(
        topic_numbers=[1, 2, 3],
        sr_questions=[{"number": "9.1", "topic": 9, "hours": 2}],
        sr_questions_hours_total=2,
        sr_table_total=2,
    )
    result = rule_r018(_ctx(rpd))
    assert result.passed is False


def test_r019_sr_must_cover_question_hours() -> None:
    rpd = RpdExtract(
        topic_numbers=[4],
        matrix_36_rows=[{"topic": 4, "lec": 2, "prac": 2, "lab": 0, "sr": 2, "total": 6}],
        sr_questions=[
            {"number": "4.1", "topic": 4, "hours": 2},
            {"number": "4.2", "topic": 4, "hours": 2},
        ],
    )
    result = rule_r019(_ctx(rpd))
    assert result.passed is False


def test_r024_pk_without_group() -> None:
    rpd = RpdExtract(pk_groups_ok=False, pk_indicators_without_group=["ПК-1.1"])
    result = rule_r024(_ctx(rpd))
    assert result.passed is False


def test_r025_lectures_practical_lab_sum() -> None:
    rpd = RpdExtract(volume=VolumeBreakdown(contact=100, lectures=40, practical=50, lab=5))
    result = rule_r025(_ctx(rpd))
    assert result.passed is False


def test_r027_sr_rows_sum() -> None:
    rpd = RpdExtract(
        sr_table_total=100,
        sr_rows=[{"label": "А", "hours": 40}, {"label": "Б", "hours": 50}],
    )
    result = rule_r027(_ctx(rpd))
    assert result.passed is False


class _MockAssessment:
    def __init__(self, form_type: str, semester: int | None) -> None:
        self.form_type = form_type
        self.semester = semester


def test_r028_passes_when_assessments_match() -> None:
    rpd = RpdExtract(
        topics31_assessments=[
            {"form_type": "exam", "semester": 1},
            {"form_type": "zachet", "semester": 2},
        ]
    )
    discipline = SimpleNamespace(
        code="X",
        name="T",
        assessments=[
            _MockAssessment("exam", 1),
            _MockAssessment("zachet", 2),
        ],
    )
    ctx = ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=discipline,
        rpd=rpd,
        plan_form="ochnaya",
    )
    result = rule_r028(ctx)
    assert result.passed is True


def test_r028_fails_on_missing_exam() -> None:
    rpd = RpdExtract(topics31_assessments=[{"form_type": "zachet", "semester": 2}])
    discipline = SimpleNamespace(
        code="X",
        name="T",
        assessments=[
            _MockAssessment("exam", 1),
            _MockAssessment("zachet", 2),
        ],
    )
    ctx = ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=discipline,
        rpd=rpd,
        plan_form="ochnaya",
    )
    result = rule_r028(ctx)
    assert result.passed is False
    assert "нет в РПД" in result.message


def test_r029_warns_on_missing_bold_titles() -> None:
    rpd = RpdExtract(topic_numbers=[1, 2], topic_titles_bold=[{"topic": 1}])
    result = rule_r029(_ctx(rpd))
    assert result.passed is False
    assert result.severity == "warning"
