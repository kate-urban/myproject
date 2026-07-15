"""Ручное снятие ошибок сверки (waivers)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlanDiscipline, ValidationWaiver
from app.services.validation.rules import RuleResult


def apply_waivers(
    results: list[RuleResult],
    waived_rule_ids: set[str] | None,
) -> list[RuleResult]:
    if not waived_rule_ids:
        return results
    updated: list[RuleResult] = []
    for item in results:
        if not item.passed and not item.skipped and item.rule_id in waived_rule_ids:
            updated.append(replace(item, passed=True, waived=True))
        else:
            updated.append(item)
    return updated


async def load_waiver_rule_ids(
    db: AsyncSession,
    program_id: UUID,
    doc_kind: str,
) -> set[str]:
    rows = (
        await db.execute(
            select(ValidationWaiver.rule_id).where(
                ValidationWaiver.program_id == program_id,
                ValidationWaiver.doc_kind == doc_kind,
            )
        )
    ).scalars().all()
    return set(rows)


async def load_waiver_rule_ids_by_program(
    db: AsyncSession,
    program_ids: list[UUID],
    doc_kind: str,
) -> dict[str, set[str]]:
    if not program_ids:
        return {}
    rows = (
        await db.execute(
            select(ValidationWaiver.program_id, ValidationWaiver.rule_id).where(
                ValidationWaiver.program_id.in_(program_ids),
                ValidationWaiver.doc_kind == doc_kind,
            )
        )
    ).all()
    result: dict[str, set[str]] = {}
    for program_id, rule_id in rows:
        key = str(program_id)
        result.setdefault(key, set()).add(rule_id)
    return result


async def create_validation_waiver(
    db: AsyncSession,
    *,
    program_id: UUID,
    doc_kind: str,
    rule_id: str,
    comment: str | None = None,
    created_by: UUID | None = None,
) -> ValidationWaiver:
    existing = (
        await db.execute(
            select(ValidationWaiver).where(
                ValidationWaiver.program_id == program_id,
                ValidationWaiver.doc_kind == doc_kind,
                ValidationWaiver.rule_id == rule_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if comment is not None:
            existing.comment = comment
        return existing

    waiver = ValidationWaiver(
        program_id=program_id,
        doc_kind=doc_kind,
        rule_id=rule_id,
        comment=comment,
        created_by=created_by,
    )
    db.add(waiver)
    await db.flush()
    return waiver


async def delete_validation_waiver(
    db: AsyncSession,
    *,
    program_id: UUID,
    doc_kind: str,
    rule_id: str,
) -> bool:
    result = await db.execute(
        delete(ValidationWaiver).where(
            ValidationWaiver.program_id == program_id,
            ValidationWaiver.doc_kind == doc_kind,
            ValidationWaiver.rule_id == rule_id,
        )
    )
    return bool(result.rowcount)


async def resolve_discipline_program(
    db: AsyncSession,
    plan_id: UUID,
    discipline_id: UUID,
) -> tuple[PlanDiscipline, UUID]:
    from sqlalchemy.orm import selectinload

    row = await db.execute(
        select(PlanDiscipline)
        .options(selectinload(PlanDiscipline.program))
        .where(
            PlanDiscipline.id == discipline_id,
            PlanDiscipline.study_plan_id == plan_id,
        )
    )
    discipline = row.scalar_one_or_none()
    if discipline is None:
        raise ValueError("Дисциплина не найдена в этом учебном плане")
    if discipline.program is None:
        raise ValueError("Программа не привязана к дисциплине")
    return discipline, discipline.program.id
