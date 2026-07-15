"""Нормализация текста по справочнику сокращений (ОПР-1 → ОПР)."""

from __future__ import annotations

import re
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tz import RefAbbreviation
from app.services.importers.dto import DisciplineDTO, StudyPlanDTO
from app.services.rpd_extractor import RpdExtract

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


async def normalize_rpd_extract(db: AsyncSession, rpd: RpdExtract) -> RpdExtract:
    """Нормализация сокращений в извлечённых полях РПД (ТЗ п. P0)."""
    rules = await load_abbreviation_rules(db)
    if not rules:
        return rpd

    discipline_name = (
        apply_abbreviation_rules(rpd.discipline_name, rules)
        if rpd.discipline_name
        else rpd.discipline_name
    )
    profile_name = (
        apply_abbreviation_rules(rpd.profile_name, rules)
        if rpd.profile_name
        else rpd.profile_name
    )
    competencies = [apply_abbreviation_rules(c, rules) for c in rpd.competencies]
    zuv_texts = [apply_abbreviation_rules(t, rules) for t in rpd.zuv_texts]
    topic_names = {
        key: apply_abbreviation_rules(value, rules)
        for key, value in rpd.topic_names.items()
    }
    section2 = {
        key: [apply_abbreviation_rules(item, rules) for item in items]
        for key, items in rpd.section2_zuv_by_indicator.items()
    }
    topics31 = [apply_abbreviation_rules(t, rules) for t in rpd.topics31_zuv_phrases]

    return replace(
        rpd,
        discipline_name=discipline_name,
        profile_name=profile_name,
        competencies=competencies,
        zuv_texts=zuv_texts,
        topic_names=topic_names,
        section2_zuv_by_indicator=section2,
        topics31_zuv_phrases=topics31,
    )
