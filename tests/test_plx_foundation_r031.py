"""Импорт блоков/циклов из .plx и правило R031."""

from __future__ import annotations

import glob
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import PlanDiscipline
from app.services.importers.plx_xml import PlxXmlReader
from app.services.importers import StudyPlanImporter
from app.services.plan_foundation import foundation_disciplines
from app.services.validation.rules import ValidationContext, rule_r031
from app.services.rpd_extractor import RpdExtract

DESIGN_PLX = next(iter(glob.glob("samples/**/M540401-2026.plx", recursive=True)), "")
DESIGN_PLX_PATH = Path(DESIGN_PLX) if DESIGN_PLX else Path("samples/M540401-2026.plx")


@pytest.mark.skipif(not DESIGN_PLX_PATH.is_file(), reason="M540401-2026.plx missing")
def test_plx_imports_block_types_from_cycles() -> None:
    dto = PlxXmlReader().read(DESIGN_PLX_PATH)
    by_code = {item.code: item for item in dto.disciplines}

    base = by_code["Б1.О.01.07"]
    assert base.block_type == "базовая"
    assert base.cycle_identifier == "Б1.О"

    variative = by_code["Б1.В.02.01"]
    assert variative.block_type == "вариативная"
    assert variative.cycle_identifier == "Б1.В"


@pytest.mark.skipif(not DESIGN_PLX_PATH.is_file(), reason="M540401-2026.plx missing")
def test_foundation_pairs_for_variative_discipline() -> None:
    dto = PlxXmlReader().read(DESIGN_PLX_PATH)
    variative = next(item for item in dto.disciplines if item.code == "Б1.В.02.01")

    class _Stub:
        pass

    plan_rows = []
    for item in dto.disciplines:
        if item.object_type not in {"2", "3", "6"}:
            continue
        row = _Stub()
        row.id = item.code
        row.code = item.code
        row.object_type = item.object_type
        row.row_order = item.row_order
        row.cycle_identifier = item.cycle_identifier
        row.block_type = item.block_type
        row.program = None
        plan_rows.append(row)

    target = next(row for row in plan_rows if row.code == variative.code)
    foundations = foundation_disciplines(target, plan_rows)
    foundation_codes = {row.code for row in foundations}

    assert "Б1.О.01.07" in foundation_codes
    assert "Б1.В.01.01" in foundation_codes
    assert variative.code not in foundation_codes


@pytest.mark.skipif(not DESIGN_PLX_PATH.is_file(), reason="M540401-2026.plx missing")
def test_rule_r031_flags_missing_base_rpd() -> None:
    dto = PlxXmlReader().read(DESIGN_PLX_PATH)
    variative = next(item for item in dto.disciplines if item.code == "Б1.В.02.01")

    class _Stub:
        pass

    plan_rows = []
    for item in dto.disciplines:
        if item.object_type not in {"2", "3", "6"}:
            continue
        row = _Stub()
        row.id = item.code
        row.code = item.code
        row.object_type = item.object_type
        row.row_order = item.row_order
        row.cycle_identifier = item.cycle_identifier
        row.block_type = item.block_type
        row.program = None
        plan_rows.append(row)

    target = next(row for row in plan_rows if row.code == variative.code)
    ctx = ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=target,
        rpd=RpdExtract(discipline_code=variative.code),
        plan_disciplines=plan_rows,
    )
    result = rule_r031(ctx)
    assert result.rule_id == "R031"
    assert not result.passed
    assert "Б1.О" in result.message or "базов" in result.message.lower()


@pytest.mark.integration
@pytest.mark.skipif(not DESIGN_PLX_PATH.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_importer_persists_block_metadata(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX_PATH, db_session)
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(PlanDiscipline).where(PlanDiscipline.study_plan_id == plan.id)
        )
    ).scalars().all()
    by_code = {row.code: row for row in rows}
    assert by_code["Б1.О.01.07"].block_type == "базовая"
    assert by_code["Б1.В.02.01"].block_type == "вариативная"
