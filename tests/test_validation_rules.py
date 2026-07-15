"""Тесты правил валидации R001–R007 и R020."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import Direction, PlanDiscipline, PlanDisciplineCompetency, Profile, StudyPlan
from app.services.rpd_extractor import RpdExtract, extract_rpd
from app.services.validation import validate_discipline

DESIGN_RPD = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "B1_O_01_07_Proektnaya_deyatelnost_k55.docx"
)


def _mock_plan(
    *,
    direction_code: str = "54.04.01",
    direction_name: str = "Дизайн",
    profile_name: str = "Экодизайн",
) -> StudyPlan:
    direction = Direction(code=direction_code, name=direction_name)
    profile = Profile(name=profile_name, direction=direction)
    return StudyPlan(
        profile=profile,
        source_file="M540401-2026.plx",
        source_format="xml_upvo",
        form="ochnaya",
    )


def _mock_discipline(**kwargs) -> PlanDiscipline:
    defaults = {
        "code": "Б1.О.01.07",
        "name": "Проектная деятельность",
        "hours_total": 396,
        "credits": 11,
        "department_code": "55",
        "in_plan": True,
    }
    defaults.update(kwargs)
    return PlanDiscipline(**defaults)


GOLDEN_COMPETENCIES = [
    "ОПК-3.1",
    "ОПК-3.2",
    "ОПК-3.3",
    "ОПК-4.4",
    "УК-2.1",
    "УК-2.2",
    "УК-2.3",
]


@pytest.mark.skipif(not DESIGN_RPD.is_file(), reason="design RPD sample missing")
def test_extract_rpd_fields_from_design_docx() -> None:
    rpd = extract_rpd(DESIGN_RPD.read_bytes(), DESIGN_RPD.name)
    assert rpd.discipline_code == "Б1.О.01.07"
    assert rpd.hours_total == 396
    assert rpd.credits == 11
    assert rpd.direction_code == "54.04.01"
    assert rpd.profile_name is not None
    assert "экодизайн" in rpd.profile_name.lower()
    assert rpd.department_code == "55"
    assert rpd.competencies
    assert "ОПК-3.1" in rpd.competencies
    assert rpd.volume.practical == 150
    assert rpd.sr_table_total == 246
    assert rpd.course_project_hours == 92


@pytest.mark.skipif(not DESIGN_RPD.is_file(), reason="design RPD sample missing")
def test_all_rules_pass_for_golden_pair() -> None:
    rpd = extract_rpd(DESIGN_RPD.read_bytes(), DESIGN_RPD.name)
    plan = _mock_plan()
    discipline = _mock_discipline(
        competencies=[
            PlanDisciplineCompetency(competency_code=code) for code in GOLDEN_COMPETENCIES
        ]
    )

    report = validate_discipline(plan, discipline, rpd)
    by_id = {item.rule_id: item for item in report.results}
    core_rules = (
        "R001",
        "R002",
        "R003",
        "R004",
        "R005",
        "R006",
        "R007",
        "R010",
        "R011",
        "R013",
        "R014",
        "R020",
        "R021",
        "R022",
        "R023",
    )
    for rule_id in core_rules:
        assert by_id[rule_id].passed is True, f"{rule_id}: {by_id[rule_id].message}"
    for rule_id in ("R015", "R016", "R017", "R018", "R019", "R024", "R025", "R026", "R027"):
        assert rule_id in by_id, f"{rule_id} missing from report"
    assert by_id["R008"].skipped is True
    assert by_id["R009"].skipped is True
    assert by_id["R012"].severity == "warning"


def test_r001_fails_on_code_mismatch() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline()
    report = validate_discipline(
        plan,
        discipline,
        RpdExtract(discipline_code="Б1.В.02.05", hours_total=396, credits=11),
    )
    r001 = next(item for item in report.results if item.rule_id == "R001")
    assert r001.passed is False


def test_r005_fails_on_credits_mismatch() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline(credits=11)
    report = validate_discipline(
        plan,
        discipline,
        RpdExtract(
            discipline_code="Б1.О.01.07",
            hours_total=396,
            credits=10,
            direction_code="54.04.01",
            profile_name="Экодизайн",
            department_code="55",
        ),
    )
    r005 = next(item for item in report.results if item.rule_id == "R005")
    assert r005.passed is False


def test_r006_fails_on_department_mismatch() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline(department_code="55")
    report = validate_discipline(
        plan,
        discipline,
        RpdExtract(
            discipline_code="Б1.О.01.07",
            hours_total=396,
            credits=11,
            direction_code="54.04.01",
            profile_name="Экодизайн",
            department_code="14",
        ),
    )
    r006 = next(item for item in report.results if item.rule_id == "R006")
    assert r006.passed is False


def test_r007_fails_when_plan_competency_missing_in_rpd() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline(
        competencies=[PlanDisciplineCompetency(competency_code="ПСК-9.9")]
    )
    report = validate_discipline(
        plan,
        discipline,
        RpdExtract(
            discipline_code="Б1.О.01.07",
            hours_total=396,
            credits=11,
            direction_code="54.04.01",
            profile_name="Экодизайн",
            department_code="55",
            competencies=["ОПК-3.1"],
        ),
    )
    r007 = next(item for item in report.results if item.rule_id == "R007")
    assert r007.passed is False


def test_r020_fails_on_hours_mismatch() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline(hours_total=396)
    report = validate_discipline(
        plan,
        discipline,
        RpdExtract(
            discipline_code="Б1.О.01.07",
            hours_total=100,
            credits=11,
            direction_code="54.04.01",
            profile_name="Экодизайн",
            department_code="55",
        ),
    )
    r020 = next(item for item in report.results if item.rule_id == "R020")
    assert r020.passed is False


MARKETING_RPD = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "B1_V_01_03_Marketing_ekologicheskikh_produktov_k51.docx"
)


@pytest.mark.skipif(not MARKETING_RPD.is_file(), reason="marketing RPD sample missing")
def test_extract_rpd_approval_year_from_signature() -> None:
    rpd = extract_rpd(MARKETING_RPD.read_bytes(), MARKETING_RPD.name)
    assert rpd.approval_year == 2024


@pytest.mark.skipif(not DESIGN_RPD.is_file(), reason="design RPD sample missing")
def test_extract_rpd_reapproval_section_without_filled_years() -> None:
    rpd = extract_rpd(DESIGN_RPD.read_bytes(), DESIGN_RPD.name)
    assert rpd.has_reapproval_section is True
    assert rpd.reapproval_years == []


def test_r012_flags_duplicate_zuv_across_indicators() -> None:
    duplicate = "способен осуществлять деловую коммуникацию в устной и письменной формах"
    report = validate_discipline(
        _mock_plan(),
        _mock_discipline(),
        RpdExtract(
            discipline_code="Б1.О.01.07",
            section2_zuv_by_indicator={
                "УК-4.1": [duplicate],
                "УК-4.2": [duplicate],
            },
        ),
    )
    r012 = next(item for item in report.results if item.rule_id == "R012")
    assert r012.passed is False
    assert "УК-4.1" in (r012.actual or "")
    assert "УК-4.2" in (r012.actual or "")

