"""Нормализация текста по справочнику сокращений (ОПР-1 → ОПР)."""

from __future__ import annotations

import re
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tz import RefAbbreviation
from app.services.importers.dto import DisciplineDTO, StudyPlanDTO

Rule = tuple[str, str, bool, int]


def apply_abbreviation_rules(text: str, rules: list[Rule]) -> str:
    if not text or not rules:
        return text
    result = text
    for pattern, replacement, is_regex, _priority in rules:
        if is_regex:
            try:
                result = re.sub(pattern, replacement, result)
            except re.error:
                continue
        else:
            result = result.replace(pattern, replacement)
    return result


async def load_abbreviation_rules(db: AsyncSession) -> list[Rule]:
    result = await db.execute(
        select(RefAbbreviation)
        .where(RefAbbreviation.is_active.is_(True))
        .order_by(RefAbbreviation.priority.desc(), RefAbbreviation.pattern)
    )
    return [
        (row.pattern, row.replacement, bool(row.is_regex), row.priority or 0)
        for row in result.scalars().all()
    ]


async def normalize_study_plan_dto(db: AsyncSession, dto: StudyPlanDTO) -> StudyPlanDTO:
    rules = await load_abbreviation_rules(db)
    if not rules:
        return dto

    disciplines: list[DisciplineDTO] = []
    for item in dto.disciplines:
        name = apply_abbreviation_rules(item.name, rules)
        dept = (
            apply_abbreviation_rules(item.department_code, rules)
            if item.department_code
            else item.department_code
        )
        comps = [apply_abbreviation_rules(c, rules) for c in item.competencies]
        disciplines.append(
            replace(
                item,
                name=name,
                department_code=dept,
                competencies=comps,
            )
        )

    return replace(
        dto,
        direction_name=apply_abbreviation_rules(dto.direction_name, rules),
        profile_name=apply_abbreviation_rules(dto.profile_name, rules),
        qualification=(
            apply_abbreviation_rules(dto.qualification, rules)
            if dto.qualification
            else dto.qualification
        ),
        disciplines=disciplines,
    )
