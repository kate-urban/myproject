"""Движок валидации ФОС ↔ РПД ↔ учебный план."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models import PlanDiscipline, Program, StudyPlan
from app.services.fos_extractor import FosExtract
from app.services.rpd_extractor import RpdExtract
from app.services.validation.fos_rules import (
    DEFAULT_FOS_ONLY_RULE_IDS,
    DEFAULT_FOS_RULE_IDS,
    FOS_RULES,
    FosValidationContext,
)
from app.services.validation.rules import RuleResult
from app.services.validation.waivers import apply_waivers


@dataclass
class FosValidationReport:
    discipline_id: UUID | None
    discipline_code: str
    rpd_document_id: str | None
    fos_document_id: str | None
    results: list[RuleResult]
    passed: bool
    skipped: bool = False
    reason: str | None = None


def _is_passed(results: list[RuleResult]) -> bool:
    active = [
        item
        for item in results
        if not item.skipped and item.severity == "critical"
    ]
    return bool(active) and all(item.passed for item in active)


def _build_context(
    plan: StudyPlan,
    discipline: PlanDiscipline,
    rpd: RpdExtract,
    fos: FosExtract,
) -> FosValidationContext:
    profile = plan.profile
    direction = profile.direction
    return FosValidationContext(
        direction_code=direction.code,
        direction_name=direction.name,
        profile_name=profile.name,
        discipline=discipline,
        rpd=rpd,
        fos=fos,
    )


def _evaluate_fos(
    ctx: FosValidationContext,
    rule_ids: list[str] | None = None,
) -> list[RuleResult]:
    selected = FOS_RULES
    if rule_ids:
        allowed = set(rule_ids)
        selected = [item for item in FOS_RULES if item[0] in allowed]
    return [checker(ctx) for _, checker in selected]


def validate_fos_bundle(
    plan: StudyPlan,
    discipline: PlanDiscipline,
    rpd: RpdExtract,
    fos: FosExtract,
    *,
    rule_ids: list[str] | None = None,
    waived_rule_ids: set[str] | None = None,
) -> FosValidationReport:
    ctx = _build_context(plan, discipline, rpd, fos)
    results = _evaluate_fos(ctx, rule_ids=rule_ids or DEFAULT_FOS_RULE_IDS)
    results = apply_waivers(results, waived_rule_ids)
    return FosValidationReport(
        discipline_id=discipline.id,
        discipline_code=discipline.code,
        rpd_document_id=None,
        fos_document_id=None,
        results=results,
        passed=_is_passed(results),
    )


def validate_fos_only_bundle(
    plan: StudyPlan,
    discipline: PlanDiscipline,
    fos: FosExtract,
    *,
    rule_ids: list[str] | None = None,
    waived_rule_ids: set[str] | None = None,
) -> FosValidationReport:
    """Валидация ФОС ↔ УП без РПД (пропуск F004, F005, F008)."""
    stub_rpd = RpdExtract(
        discipline_code=fos.discipline_code,
        direction_code=fos.direction_code,
        profile_name=fos.profile_name,
    )
    return validate_fos_bundle(
        plan,
        discipline,
        stub_rpd,
        fos,
        rule_ids=rule_ids or DEFAULT_FOS_ONLY_RULE_IDS,
        waived_rule_ids=waived_rule_ids,
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


def _fos_from_program(program: Program) -> FosExtract | None:
    if program.fos_extract_json:
        return FosExtract.from_json(program.fos_extract_json)
    return None


@dataclass
class FosPlanValidationReport:
    study_plan_id: UUID
    total_disciplines: int
    checked: int
    passed: int
    failed: int
    missing_fos: int
    fos_only: int
    passed_all: bool
    items: list[FosValidationReport]


def validate_program_fos(
    plan: StudyPlan,
    discipline: PlanDiscipline,
    program: Program,
    *,
    rule_ids: list[str] | None = None,
    waived_rule_ids: set[str] | None = None,
) -> FosValidationReport:
    if program.fos_document_id is None:
        raise ValueError("ФОС не загружена (programs.fos_document_id пуст)")

    fos = _fos_from_program(program)
    if fos is None:
        raise ValueError("Метаданные ФОС не извлечены — перезагрузите документ")

    if program.document_id is None:
        report = validate_fos_only_bundle(
            plan, discipline, fos, rule_ids=rule_ids, waived_rule_ids=waived_rule_ids
        )
        report.fos_document_id = str(program.fos_document_id)
        return report

    rpd = _rpd_from_program(program)
    if rpd is None:
        raise ValueError("Метаданные РПД не извлечены — перезагрузите документ")

    report = validate_fos_bundle(
        plan, discipline, rpd, fos, rule_ids=rule_ids, waived_rule_ids=waived_rule_ids
    )
    report.rpd_document_id = str(program.document_id)
    report.fos_document_id = str(program.fos_document_id)
    return report


def validate_study_plan_fos(
    plan: StudyPlan,
    disciplines: list[PlanDiscipline],
    *,
    rule_ids: list[str] | None = None,
    only_with_fos: bool = True,
    waivers_by_program_id: dict[str, set[str]] | None = None,
) -> FosPlanValidationReport:
    items: list[FosValidationReport] = []
    missing_fos = 0
    fos_only = 0
    passed_count = 0
    failed_count = 0

    for discipline in disciplines:
        program = discipline.program
        if program is None or program.fos_document_id is None:
            missing_fos += 1
            if only_with_fos:
                continue
            items.append(
                FosValidationReport(
                    discipline_id=discipline.id,
                    discipline_code=discipline.code,
                    rpd_document_id=None,
                    fos_document_id=None,
                    results=[],
                    passed=False,
                    skipped=True,
                    reason="missing_fos",
                )
            )
            continue

        try:
            report = validate_program_fos(
                plan,
                discipline,
                program,
                rule_ids=rule_ids,
                waived_rule_ids=(waivers_by_program_id or {}).get(str(program.id)),
            )
        except ValueError as exc:
            missing_fos += 1
            items.append(
                FosValidationReport(
                    discipline_id=discipline.id,
                    discipline_code=discipline.code,
                    rpd_document_id=(
                        str(program.document_id) if program.document_id else None
                    ),
                    fos_document_id=str(program.fos_document_id),
                    results=[],
                    passed=False,
                    skipped=True,
                    reason=str(exc),
                )
            )
            continue

        if program.document_id is None:
            fos_only += 1
        items.append(report)
        if report.passed:
            passed_count += 1
        else:
            failed_count += 1

    checked = passed_count + failed_count
    return FosPlanValidationReport(
        study_plan_id=plan.id,
        total_disciplines=len(disciplines),
        checked=checked,
        passed=passed_count,
        failed=failed_count,
        missing_fos=missing_fos,
        fos_only=fos_only,
        passed_all=checked > 0 and failed_count == 0,
        items=items,
    )
