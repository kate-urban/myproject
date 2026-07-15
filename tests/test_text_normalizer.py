"""Тесты нормализатора сокращений при импорте УП."""

from __future__ import annotations

import pytest

from app.services.importers.dto import DisciplineDTO, StudyPlanDTO
from app.services.text_normalizer import apply_abbreviation_rules


def test_apply_literal_abbreviation() -> None:
    rules = [("ОПР-1", "ОПР", False, 100)]
    assert apply_abbreviation_rules("Кафедра ОПР-1", rules) == "Кафедра ОПР"


def test_apply_regex_abbreviation() -> None:
    rules = [(r"ОПР-\d+", "ОПР", True, 90)]
    assert apply_abbreviation_rules("ОПР-12 и ОПР-3", rules) == "ОПР и ОПР"


@pytest.mark.asyncio
async def test_normalize_study_plan_dto(db_session) -> None:
    from app.services.reference_seed import seed_reference_defaults
    from app.services.text_normalizer import normalize_study_plan_dto

    await seed_reference_defaults(db_session)
    await db_session.commit()

    dto = StudyPlanDTO(
        source_file="test.plx",
        source_format="xml_upvo",
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Профиль",
        form="ochnaya",
        year=2026,
        disciplines=[
            DisciplineDTO(code="Б1.О.01", name="Дисциплина ОПР-1", competencies=["ОПР-1.1"]),
        ],
    )
    normalized = await normalize_study_plan_dto(db_session, dto)
    assert normalized.disciplines[0].name == "Дисциплина ОПР"
    assert normalized.disciplines[0].competencies == ["ОПР.1"]
