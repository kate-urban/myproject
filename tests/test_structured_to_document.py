"""Запись structured tables в HTML разделы."""

from __future__ import annotations

import uuid

import pytest

from app.services.structured_to_document import (
    _literature_html,
    _topics_table_html,
    _zuv_table_html,
)


def test_topics_table_html_renders_rows() -> None:
    html = _topics_table_html(
        [
            {
                "topic_number": "1",
                "title": "Введение",
                "semester": 1,
                "hours_lecture": 4,
                "hours_practical": 2,
                "hours_lab": None,
                "hours_sr": 6,
            }
        ]
    )
    assert "Введение" in html
    assert "<table" in html


def test_zuv_table_html_renders_type_label() -> None:
    html = _zuv_table_html(
        [{"indicator_code": "ОПК-1", "zuv_type": "know", "text": "Знает основы", "topic_ref": "1"}]
    )
    assert "Знать" in html
    assert "ОПК-1" in html


def test_literature_html_renders_numbered_list() -> None:
    html = _literature_html([{"citation": "Иванов И.И. Учебник.", "lit_type": "main"}])
    assert "1." in html
    assert "Учебник" in html


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_structured_to_document_updates_section(db_session) -> None:
    import glob
    from pathlib import Path
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Document as DocumentModel
    from app.models import PlanDiscipline, Program, Section
    from app.services.importers import StudyPlanImporter
    from app.services.program_content import replace_program_topics
    from app.services.structured_to_document import apply_structured_to_document

    plx = next(iter(glob.glob("samples/**/M540401-2026.plx", recursive=True)), "")
    if not plx:
        pytest.skip("M540401-2026.plx missing")

    importer = StudyPlanImporter()
    plan = await importer.import_file(Path(plx), db_session)
    discipline = (
        await db_session.execute(
            select(PlanDiscipline)
            .options(selectinload(PlanDiscipline.program))
            .where(PlanDiscipline.study_plan_id == plan.id)
            .limit(1)
        )
    ).scalar_one()
    program = discipline.program
    if program is None:
        program = Program(id=uuid.uuid4(), plan_discipline_id=discipline.id, status="uploaded")
        db_session.add(program)
        discipline.program = program
    doc = DocumentModel(id=uuid.uuid4(), filename="test.docx")
    db_session.add(doc)
    program.document_id = doc.id
    section = Section(
        id=uuid.uuid4(),
        document_id=doc.id,
        section_name="3.1 Содержание дисциплины",
        content="<p>старое</p>",
        order_index=1,
        level=1,
    )
    db_session.add(section)
    await db_session.flush()

    await replace_program_topics(
        db_session,
        program.id,
        [{"topic_number": "1", "title": "Тема из structured", "semester": 1}],
    )
    result = await apply_structured_to_document(db_session, program.id)
    await db_session.flush()

    updated = (
        await db_session.execute(select(Section).where(Section.id == section.id))
    ).scalar_one()
    assert "Тема из structured" in (updated.content or "")
    assert result["updated_sections"]
