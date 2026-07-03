"""Общие хелперы для golden-тестов ФОС."""

from __future__ import annotations

from app.models import Direction, PlanDiscipline, PlanDisciplineCompetency, Profile, StudyPlan
from app.services.importers import StudyPlanImporter
from tests.golden_fos_data import GoldenFosPair


def failed_critical_rules(report) -> list[str]:
    return [
        item.rule_id
        for item in report.results
        if not item.skipped and item.severity == "critical" and not item.passed
    ]


def plan_and_discipline_from_pair(pair: GoldenFosPair) -> tuple[StudyPlan, PlanDiscipline]:
    plan_dto = StudyPlanImporter().read_dto(pair.plx_path)
    direction = Direction(code=plan_dto.direction_code, name=plan_dto.direction_name)
    profile = Profile(name=plan_dto.profile_name, direction=direction)
    plan = StudyPlan(
        profile=profile,
        source_file=plan_dto.source_file,
        source_format=plan_dto.source_format,
        form=plan_dto.form,
    )
    dto_disc = next(d for d in plan_dto.disciplines if d.code == pair.discipline_code)
    discipline = PlanDiscipline(
        code=dto_disc.code,
        name=dto_disc.name,
        hours_total=dto_disc.hours_total,
        credits=dto_disc.credits,
        department_code=dto_disc.department_code,
        in_plan=True,
        competencies=[
            PlanDisciplineCompetency(competency_code=code) for code in dto_disc.competencies
        ],
    )
    return plan, discipline
