"""Движок валидации: РПД ↔ дисциплина учебного плана."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models import PlanDiscipline, Program, StudyPlan
from app.services.rpd_extractor import RpdExtract
from app.services.validation.rules import (
    DEFAULT_RULE_IDS,
    RULES,
    RuleResult,
    ValidationContext,
)


@dataclass
class ValidationReport:
    discipline_id: UUID | None
    discipline_code: str
    document_id: str | None
    results: list[RuleResult]
    passed: bool
    skipped: bool = False
    reason: str | None = None


@dataclass
class PlanValidationReport:
    study_plan_id: UUID
    total_disciplines: int
    checked: int
    passed: int
    failed: int
    missing_rpd: int
    passed_all: bool
    items: list[ValidationReport]


def _build_context(plan: StudyPlan, discipline: PlanDiscipline, rpd: RpdExtract) -> ValidationContext:
    profile = plan.profile
    direction = profile.direction
    return ValidationContext(
        direction_code=direction.code,
        direction_name=direction.name,
        profile_name=profile.name,
        discipline=discipline,
        rpd=rpd,
    )


def _rpd_from_program(program: Program) -> RpdExtract | None:
    if program.rpd_extract_json:
        parsed = RpdExtract.from_json(program.rpd_extract_json)
        if parsed:
            return parsed

    if not program.rpd_discipline_code and program.rpd_hours_total is None:
        return None

    return RpdExtract(
        discipline_code=program.rpd_discipline_code,
        discipline_name=program.rpd_discipline_name,
        direction_code=program.rpd_direction_code,
        profile_name=program.rpd_profile_name,
        department_code=program.rpd_department_code,
        hours_total=program.rpd_hours_total,
        credits=program.rpd_credits,
        competencies=(
            program.rpd_competencies.split(";")
            if program.rpd_competencies
            else []
        ),
    )


def _evaluate(ctx: ValidationContext, rule_ids: list[str] | None = None) -> list[RuleResult]:
    selected = RULES
    if rule_ids:
        allowed = set(rule_ids)
        selected = [item for item in RULES if item[0] in allowed]
    return [checker(ctx) for _, checker in selected]


def _is_passed(results: list[RuleResult]) -> bool:
    active = [
        item
        for item in results
        if not item.skipped and item.severity == "critical"
    ]
    return bool(active) and all(item.passed for item in active)


def validate_discipline(
    plan: StudyPlan,
    discipline: PlanDiscipline,
    rpd: RpdExtract,
    *,
    rule_ids: list[str] | None = None,
) -> ValidationReport:
    ctx = _build_context(plan, discipline, rpd)
    results = _evaluate(ctx, rule_ids=rule_ids or DEFAULT_RULE_IDS)
    return ValidationReport(
        discipline_id=discipline.id,
        discipline_code=discipline.code,
        document_id=None,
        results=results,
        passed=_is_passed(results),
    )


def validate_program(
    plan: StudyPlan,
    discipline: PlanDiscipline,
    program: Program,
    *,
    rule_ids: list[str] | None = None,
) -> ValidationReport:
    if program.document_id is None:
        raise ValueError("РПД не загружена (programs.document_id пуст)")

    rpd = _rpd_from_program(program)
    if rpd is None:
        raise ValueError("Метаданные РПД не извлечены — перезагрузите документ")

    report = validate_discipline(plan, discipline, rpd, rule_ids=rule_ids)
    report.document_id = str(program.document_id)
    return report


def validate_study_plan(
    plan: StudyPlan,
    disciplines: list[PlanDiscipline],
    *,
    rule_ids: list[str] | None = None,
    only_with_rpd: bool = True,
) -> PlanValidationReport:
    selected_rules = rule_ids or DEFAULT_RULE_IDS
    items: list[ValidationReport] = []
    missing_rpd = 0
    passed_count = 0
    failed_count = 0

    for discipline in disciplines:
        program = discipline.program
        if program is None or program.document_id is None:
            missing_rpd += 1
            if only_with_rpd:
                continue
            items.append(
                ValidationReport(
                    discipline_id=discipline.id,
                    discipline_code=discipline.code,
                    document_id=None,
                    results=[],
                    passed=False,
                    skipped=True,
                    reason="missing_rpd",
                )
            )
            continue

        try:
            report = validate_program(
                plan,
                discipline,
                program,
                rule_ids=selected_rules,
            )
        except ValueError as exc:
            missing_rpd += 1
            items.append(
                ValidationReport(
                    discipline_id=discipline.id,
                    discipline_code=discipline.code,
                    document_id=str(program.document_id) if program.document_id else None,
                    results=[],
                    passed=False,
                    skipped=True,
                    reason=str(exc),
                )
            )
            continue

        items.append(report)
        if report.passed:
            passed_count += 1
        else:
            failed_count += 1

    checked = passed_count + failed_count
    return PlanValidationReport(
        study_plan_id=plan.id,
        total_disciplines=len(disciplines),
        checked=checked,
        passed=passed_count,
        failed=failed_count,
        missing_rpd=missing_rpd,
        passed_all=checked > 0 and failed_count == 0,
        items=items,
    )
