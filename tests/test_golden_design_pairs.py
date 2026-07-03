"""Тесты эталонных пар 54.04.01: M540401-2026.plx ↔ DOCX из golden_pairs.yaml."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Document, PlanDiscipline, Profile, StudyPlan
from app.services.importers import StudyPlanImporter
from app.services.rpd_extractor import extract_rpd
from app.services.rpd_linker import link_document_to_program
from app.services.validation import validate_program
from app.utils.discipline_code import resolve_discipline_code
from tests.golden_design_data import (
    DESIGN_PLX,
    GOLDEN_DESIGN_PAIRS,
    GoldenDesignPair,
)


def _discipline_from_dto(dto, code: str):
    return next(item for item in dto.disciplines if item.code == code)


def _failed_critical_rules(report) -> list[str]:
    return [
        item.rule_id
        for item in report.results
        if not item.skipped and item.severity == "critical" and not item.passed
    ]


@pytest.fixture(scope="module")
def design_dto():
    if not DESIGN_PLX.is_file():
        pytest.skip("samples/M540401-2026.plx missing")
    return StudyPlanImporter().read_dto(DESIGN_PLX)


@pytest.mark.parametrize("pair", GOLDEN_DESIGN_PAIRS, ids=[p.id for p in GOLDEN_DESIGN_PAIRS])
def test_plx_discipline_matches_golden(design_dto, pair: GoldenDesignPair) -> None:
    discipline = _discipline_from_dto(design_dto, pair.discipline_code)
    assert discipline.name == pair.discipline_name
    assert discipline.credits == pair.credits
    assert discipline.hours_total == pair.hours_total
    assert discipline.department_code == pair.department_code


@pytest.mark.parametrize("pair", GOLDEN_DESIGN_PAIRS, ids=[p.id for p in GOLDEN_DESIGN_PAIRS])
def test_rpd_passport_code_matches_golden(pair: GoldenDesignPair) -> None:
    if not pair.files_present:
        pytest.skip(f"sample files missing for {pair.id}")

    file_bytes = pair.rpd_path.read_bytes()
    code = resolve_discipline_code(file_bytes, pair.rpd_path.name)
    assert code == pair.discipline_code

    rpd = extract_rpd(file_bytes, pair.rpd_path.name)
    assert rpd.discipline_code == pair.discipline_code
    assert rpd.credits == pair.credits
    assert rpd.department_code == pair.department_code
    if rpd.hours_total is not None:
        assert rpd.hours_total == pair.hours_total


@pytest.mark.integration
@pytest.mark.parametrize("pair", GOLDEN_DESIGN_PAIRS, ids=[p.id for p in GOLDEN_DESIGN_PAIRS])
@pytest.mark.asyncio
async def test_golden_pair_link_and_validate(db_session, pair: GoldenDesignPair) -> None:
    if not pair.files_present:
        pytest.skip(f"sample files missing for {pair.id}")

    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    document_id = uuid.uuid4()
    file_bytes = pair.rpd_path.read_bytes()
    db_session.add(
        Document(id=document_id, filename=pair.rpd_path.name, doc_type="rpd")
    )
    await db_session.flush()

    link = await link_document_to_program(
        db_session,
        document_id=document_id,
        study_plan_id=plan.id,
        file_bytes=file_bytes,
        filename=pair.rpd_path.name,
    )
    await db_session.commit()

    assert link.linked is True
    assert link.discipline_code == pair.discipline_code

    discipline = (
        await db_session.execute(
            select(PlanDiscipline)
            .options(
                selectinload(PlanDiscipline.program),
                selectinload(PlanDiscipline.competencies),
            )
            .where(
                PlanDiscipline.study_plan_id == plan.id,
                PlanDiscipline.code == pair.discipline_code,
            )
        )
    ).scalar_one()

    plan_loaded = (
        await db_session.execute(
            select(StudyPlan)
            .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
            .where(StudyPlan.id == plan.id)
        )
    ).scalar_one()

    report = validate_program(plan_loaded, discipline, discipline.program)
    failed = _failed_critical_rules(report)

    if pair.validation_passes:
        assert report.passed is True, f"failed rules: {failed}"
        assert not failed
    else:
        assert report.passed is False
        assert failed
        assert set(failed) == set(pair.known_failures), (
            f"expected {pair.known_failures}, got {failed}"
        )
