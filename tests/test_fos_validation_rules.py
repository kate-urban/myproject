"""Тесты правил валидации F001–F010."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import Direction, PlanDiscipline, PlanDisciplineCompetency, Profile, StudyPlan
from app.services.fos_extractor import FosExtract, FosGradingCriterion, extract_fos
from app.services.rpd_extractor import RpdExtract, extract_rpd
from app.services.validation import validate_fos_bundle

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
RPD_FTD01 = SAMPLES / "FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx"
FOS_FTD01 = SAMPLES / "FOS_FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx"


def _mock_plan() -> StudyPlan:
    direction = Direction(code="54.04.01", name="Дизайн")
    profile = Profile(name="Экодизайн", direction=direction)
    return StudyPlan(
        profile=profile,
        source_file="M540401-2026.plx",
        source_format="xml_upvo",
        form="ochnaya",
    )


def _mock_discipline() -> PlanDiscipline:
    return PlanDiscipline(
        code="ФТД.01",
        name="История развития науки и техники",
        hours_total=72,
        credits=2,
        department_code="52",
        in_plan=True,
        competencies=[PlanDisciplineCompetency(competency_code="УК-5.1")],
    )


@pytest.mark.skipif(
    not (RPD_FTD01.is_file() and FOS_FTD01.is_file()),
    reason="FTD.01 rpd/fos samples missing",
)
def test_all_f_rules_pass_for_golden_triple() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline()
    rpd = extract_rpd(RPD_FTD01.read_bytes(), RPD_FTD01.name)
    fos = extract_fos(FOS_FTD01.read_bytes(), FOS_FTD01.name)

    report = validate_fos_bundle(plan, discipline, rpd, fos)
    by_id = {item.rule_id: item for item in report.results}

    assert report.passed is True
    for rule_id in (
        "F001",
        "F002",
        "F003",
        "F004",
        "F005",
        "F006",
        "F007",
        "F008",
        "F009",
        "F010",
        "F011",
        "F012",
        "F013",
        "F014",
    ):
        assert by_id[rule_id].passed is True, f"{rule_id}: {by_id[rule_id].message}"


def test_f001_fails_on_code_mismatch() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline()
    report = validate_fos_bundle(
        plan,
        discipline,
        RpdExtract(
            discipline_code="ФТД.01",
            direction_code="54.04.01",
            profile_name="Экодизайн",
            competencies=["УК-5.1"],
        ),
        FosExtract(
            discipline_code="ФТД.04",
            direction_code="54.04.01",
            profile_name="Экодизайн",
            indicators=["УК-5.1"],
            grading_criteria=[FosGradingCriterion(description="test")],
        ),
    )
    f001 = next(item for item in report.results if item.rule_id == "F001")
    assert f001.passed is False
