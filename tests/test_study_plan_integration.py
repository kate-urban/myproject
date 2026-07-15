"""Интеграционные тесты: импорт УП + GET API + связка РПД."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Document, PlanDiscipline, Profile, Program, StudyPlan
from app.services.importers import StudyPlanImporter
from app.services.rpd_linker import link_document_to_program
from app.services.validation import validate_program, validate_study_plan, CORE_RULE_IDS
from app.utils.discipline_code import code_from_filename, resolve_discipline_code

DESIGN_PLX = Path(__file__).resolve().parents[1] / "samples" / "M540401-2026.plx"
DESIGN_RPD = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "B1_O_01_07_Proektnaya_deyatelnost_k55.docx"
)


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_import_m540401_discipline_in_db(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    result = await db_session.execute(
        select(PlanDiscipline).where(
            PlanDiscipline.study_plan_id == plan.id,
            PlanDiscipline.code == "Б1.О.01.07",
        )
    )
    discipline = result.scalar_one()

    assert discipline.credits == 11
    assert discipline.hours_total == 396
    assert discipline.department_code == "55"


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_get_disciplines_via_query(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    result = await db_session.execute(
        select(PlanDiscipline)
        .options(selectinload(PlanDiscipline.competencies))
        .where(PlanDiscipline.study_plan_id == plan.id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = result.scalars().all()
    assert len(disciplines) >= 20
    assert any(d.code == "Б1.О.01.07" for d in disciplines)


@pytest.mark.skipif(
    not DESIGN_PLX.is_file() or not DESIGN_RPD.is_file(),
    reason="design plx/docx pair missing",
)
@pytest.mark.asyncio
async def test_upload_rpd_links_program(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    file_bytes = DESIGN_RPD.read_bytes()
    code = resolve_discipline_code(file_bytes, DESIGN_RPD.name)
    assert code == "Б1.О.01.07"

    document_id = uuid.uuid4()
    db_session.add(
        Document(id=document_id, filename=DESIGN_RPD.name, doc_type="rpd")
    )
    await db_session.flush()

    link = await link_document_to_program(
        db_session,
        document_id=document_id,
        study_plan_id=plan.id,
        file_bytes=file_bytes,
        filename=DESIGN_RPD.name,
    )
    await db_session.commit()

    assert link.linked is True
    assert link.discipline_code == "Б1.О.01.07"
    assert link.program_status == "uploaded"

    result = await db_session.execute(
        select(Program)
        .join(PlanDiscipline)
        .where(
            PlanDiscipline.study_plan_id == plan.id,
            PlanDiscipline.code == "Б1.О.01.07",
        )
    )
    program = result.scalar_one()
    assert program.document_id == document_id
    assert program.status == "uploaded"
    assert program.rpd_discipline_code == "Б1.О.01.07"
    assert program.rpd_hours_total == 396
    assert program.rpd_department_code == "55"
    assert program.rpd_direction_code == "54.04.01"
    assert program.rpd_extract_json


@pytest.mark.skipif(
    not DESIGN_PLX.is_file() or not DESIGN_RPD.is_file(),
    reason="design plx/docx pair missing",
)
@pytest.mark.asyncio
async def test_validate_design_b1o0107_r001_r020(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    file_bytes = DESIGN_RPD.read_bytes()
    document_id = uuid.uuid4()
    db_session.add(
        Document(id=document_id, filename=DESIGN_RPD.name, doc_type="rpd")
    )
    await db_session.flush()

    await link_document_to_program(
        db_session,
        document_id=document_id,
        study_plan_id=plan.id,
        file_bytes=file_bytes,
        filename=DESIGN_RPD.name,
    )
    await db_session.commit()

    discipline = (
        await db_session.execute(
            select(PlanDiscipline)
            .options(
                selectinload(PlanDiscipline.program),
                selectinload(PlanDiscipline.competencies),
                selectinload(PlanDiscipline.assessments),
            )
            .where(
                PlanDiscipline.study_plan_id == plan.id,
                PlanDiscipline.code == "Б1.О.01.07",
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

    report = validate_program(
        plan_loaded, discipline, discipline.program, rule_ids=CORE_RULE_IDS
    )
    assert report.passed is True
    critical = [
        item for item in report.results if not item.skipped and item.severity == "critical"
    ]
    assert critical
    assert all(item.passed for item in critical)
    assert any(item.rule_id == "R021" and item.passed for item in report.results)


@pytest.mark.skipif(
    not DESIGN_PLX.is_file() or not DESIGN_RPD.is_file(),
    reason="design plx/docx pair missing",
)
@pytest.mark.asyncio
async def test_validate_study_plan_batch(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    file_bytes = DESIGN_RPD.read_bytes()
    document_id = uuid.uuid4()
    db_session.add(
        Document(id=document_id, filename=DESIGN_RPD.name, doc_type="rpd")
    )
    await db_session.flush()

    await link_document_to_program(
        db_session,
        document_id=document_id,
        study_plan_id=plan.id,
        file_bytes=file_bytes,
        filename=DESIGN_RPD.name,
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
                selectinload(PlanDiscipline.assessments),
            )
            .where(PlanDiscipline.study_plan_id == plan.id)
        )
    ).scalars().all()

    report = validate_study_plan(plan_loaded, list(disciplines), rule_ids=CORE_RULE_IDS)
    assert report.checked == 1
    assert report.passed == 1
    assert report.failed == 0
    assert report.passed_all is True
    assert report.items[0].discipline_code == "Б1.О.01.07"


def test_code_from_filename_examples() -> None:
    assert code_from_filename("B1_O_01_07_Proektnaya_deyatelnost_k55.docx") == "Б1.О.01.07"
    assert (
        code_from_filename(
            "B2_O_03_P_Proizvodstvennaya_praktika_Proektnaya_praktika_k55.docx"
        )
        == "Б2.О.03(П)"
    )
    assert (
        code_from_filename("B1_V_DV_01_01_Innovatsionny_menedzhment_k51.docx")
        == "Б1.В.ДВ.01.01"
    )
