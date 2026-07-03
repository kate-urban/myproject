"""Интеграционные тесты golden-пар plx + rpd/fos (шаг 3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Document, PlanDiscipline, Profile, StudyPlan
from app.services.fos_extractor import extract_fos
from app.services.importers import StudyPlanImporter
from app.services.rpd_extractor import extract_rpd
from app.services.rpd_linker import link_document_to_program
from app.services.validation import (
    validate_fos_bundle,
    validate_fos_only_bundle,
    validate_program_fos,
    validate_study_plan_fos,
)
from tests.golden_fos_data import (
    GOLDEN_FOS_ONLY_PAIRS,
    GOLDEN_FOS_PAIRS,
    GOLDEN_FOS_TRIPLE_PAIRS,
    GoldenFosPair,
)
from tests.golden_fos_helpers import failed_critical_rules, plan_and_discipline_from_pair


@pytest.mark.parametrize("pair", GOLDEN_FOS_PAIRS, ids=[p.id for p in GOLDEN_FOS_PAIRS])
def test_fos_extract_matches_golden(pair: GoldenFosPair) -> None:
    if not pair.files_present:
        pytest.skip(f"sample files missing for {pair.id}")

    fos = extract_fos(pair.fos_path.read_bytes(), pair.fos_path.name)
    assert fos.discipline_code == pair.discipline_code
    assert fos.control_items
    assert fos.grading_criteria

    if pair.plan_competencies:
        for code in pair.plan_competencies:
            assert code in fos.indicators or code in fos.competencies


@pytest.mark.parametrize("pair", GOLDEN_FOS_PAIRS, ids=[p.id for p in GOLDEN_FOS_PAIRS])
def test_fos_bundle_validate_without_db(pair: GoldenFosPair) -> None:
    if not pair.files_present:
        pytest.skip(f"sample files missing for {pair.id}")

    plan, discipline = plan_and_discipline_from_pair(pair)
    fos = extract_fos(pair.fos_path.read_bytes(), pair.fos_path.name)

    if pair.fos_only:
        report = validate_fos_only_bundle(plan, discipline, fos)
    else:
        rpd = extract_rpd(pair.rpd_path.read_bytes(), pair.rpd_path.name)
        report = validate_fos_bundle(plan, discipline, rpd, fos)

    failed = failed_critical_rules(report)
    if pair.validation_passes:
        assert report.passed is True, f"failed rules: {failed}"
        assert not failed
    else:
        assert report.passed is False
        assert set(failed) == set(pair.expected_fail_rules), failed


@pytest.mark.integration
@pytest.mark.parametrize("pair", GOLDEN_FOS_TRIPLE_PAIRS, ids=[p.id for p in GOLDEN_FOS_TRIPLE_PAIRS])
@pytest.mark.asyncio
async def test_golden_fos_triple_link_and_validate(db_session, pair: GoldenFosPair) -> None:
    if not pair.files_present:
        pytest.skip(f"sample files missing for {pair.id}")

    importer = StudyPlanImporter()
    plan = await importer.import_file(pair.plx_path, db_session)

    rpd_doc_id = uuid.uuid4()
    fos_doc_id = uuid.uuid4()
    db_session.add(Document(id=rpd_doc_id, filename=pair.rpd_file, doc_type="rpd"))
    db_session.add(Document(id=fos_doc_id, filename=pair.fos_file, doc_type="fos"))
    await db_session.flush()

    rpd_link = await link_document_to_program(
        db_session,
        document_id=rpd_doc_id,
        study_plan_id=plan.id,
        file_bytes=pair.rpd_path.read_bytes(),
        filename=pair.rpd_path.name,
    )
    fos_link = await link_document_to_program(
        db_session,
        document_id=fos_doc_id,
        study_plan_id=plan.id,
        file_bytes=pair.fos_path.read_bytes(),
        filename=pair.fos_path.name,
    )
    await db_session.commit()

    assert rpd_link.linked is True
    assert fos_link.linked is True
    assert rpd_link.doc_kind == "rpd"
    assert fos_link.doc_kind == "fos"

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

    report = validate_program_fos(plan_loaded, discipline, discipline.program)
    failed = failed_critical_rules(report)

    if pair.validation_passes:
        assert report.passed is True, f"failed rules: {failed}"
        assert not failed
    else:
        assert report.passed is False
        assert failed


@pytest.mark.integration
@pytest.mark.parametrize("pair", GOLDEN_FOS_ONLY_PAIRS, ids=[p.id for p in GOLDEN_FOS_ONLY_PAIRS])
@pytest.mark.asyncio
async def test_golden_fos_only_link_and_validate(db_session, pair: GoldenFosPair) -> None:
    if not pair.files_present:
        pytest.skip(f"sample files missing for {pair.id}")

    importer = StudyPlanImporter()
    plan = await importer.import_file(pair.plx_path, db_session)

    fos_doc_id = uuid.uuid4()
    db_session.add(Document(id=fos_doc_id, filename=pair.fos_file, doc_type="fos"))
    await db_session.flush()

    fos_link = await link_document_to_program(
        db_session,
        document_id=fos_doc_id,
        study_plan_id=plan.id,
        file_bytes=pair.fos_path.read_bytes(),
        filename=pair.fos_path.name,
    )
    await db_session.commit()

    assert fos_link.linked is True
    assert fos_link.doc_kind == "fos"

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

    report = validate_program_fos(plan_loaded, discipline, discipline.program)
    failed = failed_critical_rules(report)
    assert report.passed is True, f"failed rules: {failed}"
    assert discipline.program.document_id is None
    assert discipline.program.fos_document_id == fos_doc_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validate_study_plan_fos_batch(db_session) -> None:
    pair = next(p for p in GOLDEN_FOS_TRIPLE_PAIRS if p.id == "design_ftd01")
    if not pair.files_present:
        pytest.skip("design_ftd01 samples missing")

    importer = StudyPlanImporter()
    plan = await importer.import_file(pair.plx_path, db_session)

    rpd_doc_id = uuid.uuid4()
    fos_doc_id = uuid.uuid4()
    db_session.add(Document(id=rpd_doc_id, filename=pair.rpd_file, doc_type="rpd"))
    db_session.add(Document(id=fos_doc_id, filename=pair.fos_file, doc_type="fos"))
    await db_session.flush()

    await link_document_to_program(
        db_session,
        document_id=rpd_doc_id,
        study_plan_id=plan.id,
        file_bytes=pair.rpd_path.read_bytes(),
        filename=pair.rpd_path.name,
    )
    await link_document_to_program(
        db_session,
        document_id=fos_doc_id,
        study_plan_id=plan.id,
        file_bytes=pair.fos_path.read_bytes(),
        filename=pair.fos_path.name,
    )
    await db_session.commit()

    plan_loaded = (
        await db_session.execute(
            select(StudyPlan)
            .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
            .where(StudyPlan.id == plan.id)
        )
    ).scalar_one()

    disciplines = (
        await db_session.execute(
            select(PlanDiscipline)
            .options(
                selectinload(PlanDiscipline.program),
                selectinload(PlanDiscipline.competencies),
            )
            .where(PlanDiscipline.study_plan_id == plan.id)
        )
    ).scalars().all()

    report = validate_study_plan_fos(plan_loaded, list(disciplines))
    assert report.checked == 1
    assert report.passed == 1
    assert report.failed == 0
    assert report.fos_only == 0
    assert report.passed_all is True
    assert report.items[0].discipline_code == pair.discipline_code
