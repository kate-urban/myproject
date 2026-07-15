"""Импорт УП с повторяющимися кодами дисциплин в .plx."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import PlanDiscipline
from app.services.importers import StudyPlanImporter
from app.services.importers.dto import DisciplineDTO, StudyPlanDTO
from app.services.importers.study_plan_importer import dedupe_discipline_dtos

DESIGN_PLX = __import__("pathlib").Path(__file__).resolve().parents[1] / "samples" / "M540401-2026.plx"


def test_dedupe_discipline_dtos_merges_same_code() -> None:
    items = [
        DisciplineDTO(code="Б1.О.01", name="Блок", row_order=1, hours_total=0),
        DisciplineDTO(
            code="Б1.О.01",
            name="Иностранный язык",
            row_order=2,
            hours_total=252,
            credits=7.0,
            competencies=["ОПК-1"],
        ),
    ]
    merged = dedupe_discipline_dtos(items)
    assert len(merged) == 1
    assert merged[0].code == "Б1.О.01"
    assert merged[0].name == "Иностранный язык"
    assert merged[0].hours_total == 252
    assert merged[0].competencies == ["ОПК-1"]


@pytest.mark.asyncio
async def test_import_plan_with_duplicate_codes_in_dto(db_session) -> None:
    importer = StudyPlanImporter()
    base = importer.read_dto(DESIGN_PLX)
    duplicate = DisciplineDTO(
        code=base.disciplines[0].code,
        name=base.disciplines[0].name,
        row_order=base.disciplines[0].row_order + 1,
        hours_total=base.disciplines[0].hours_total,
        credits=base.disciplines[0].credits,
    )
    dto = StudyPlanDTO(
        source_file=base.source_file,
        source_format=base.source_format,
        direction_code=base.direction_code,
        direction_name=base.direction_name,
        profile_name=base.profile_name,
        form=base.form,
        year=base.year,
        qualification=base.qualification,
        fgos_number=base.fgos_number,
        disciplines=[*base.disciplines, duplicate],
    )

    plan = await importer.import_dto(dto, db_session)
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(PlanDiscipline)
            .where(PlanDiscipline.study_plan_id == plan.id)
        )
    ).scalar_one()
    assert count == len(base.disciplines)
