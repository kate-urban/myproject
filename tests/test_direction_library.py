"""Тесты библиотеки направления и copy-on-write."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models import Document, PlanDiscipline, Program, Section, StudyPlan
from app.models_tz import DirectionProgramLibrary
from app.services.document_fork import (
    clone_document_with_sections,
    count_document_program_refs,
    fork_document_for_program,
)

pytestmark = pytest.mark.asyncio


async def test_fork_document_when_shared(db_session) -> None:
    from app.models import Direction, Profile

    direction = Direction(id=uuid.uuid4(), code=f"T{uuid.uuid4().hex[:6]}", name="Test")
    profile = Profile(id=uuid.uuid4(), direction_id=direction.id, name="Prof")
    plan = StudyPlan(
        id=uuid.uuid4(),
        profile_id=profile.id,
        source_file="test.plx",
        source_format="xml_upvo",
        form="ochnaya",
        year=2024,
    )
    doc_id = uuid.uuid4()
    db_session.add_all([direction, profile, plan])
    db_session.add(Document(id=doc_id, filename="test.docx", doc_type="rp"))
    db_session.add(
        Section(
            id=uuid.uuid4(),
            document_id=doc_id,
            section_name="Intro",
            content="<p>Hello</p>",
            content_plain="Hello",
            level=1,
            order_index=0,
        )
    )

    disciplines = []
    programs = []
    plan_id = plan.id
    for i in range(2):
        disc = PlanDiscipline(
            id=uuid.uuid4(),
            study_plan_id=plan_id,
            code=f"Б1.О.0{i+1}",
            name=f"Disc {i}",
            row_order=i,
        )
        prog = Program(
            id=uuid.uuid4(),
            plan_discipline_id=disc.id,
            document_id=doc_id,
            status="uploaded",
        )
        disc.program = prog
        disciplines.append(disc)
        programs.append(prog)
    db_session.add_all(disciplines + programs)
    await db_session.flush()

    assert await count_document_program_refs(db_session, doc_id) == 2

    new_doc_id = await fork_document_for_program(
        db_session,
        document_id=doc_id,
        program_id=programs[0].id,
    )
    assert new_doc_id != doc_id
    assert programs[0].document_id == new_doc_id
    assert programs[1].document_id == doc_id

    old_sections = (
        await db_session.execute(select(func.count()).select_from(Section).where(Section.document_id == doc_id))
    ).scalar_one()
    new_sections = (
        await db_session.execute(select(func.count()).select_from(Section).where(Section.document_id == new_doc_id))
    ).scalar_one()
    assert old_sections == 1
    assert new_sections == 1


async def test_clone_document_creates_independent_copy(db_session) -> None:
    doc_id = uuid.uuid4()
    db_session.add(Document(id=doc_id, filename="a.docx", doc_type="rp"))
    sec_id = uuid.uuid4()
    db_session.add(
        Section(
            id=sec_id,
            document_id=doc_id,
            section_name="S1",
            content="x",
            content_plain="x",
            level=1,
            order_index=0,
        )
    )
    await db_session.flush()

    copy_id = await clone_document_with_sections(db_session, doc_id)
    assert copy_id != doc_id

    sec = await db_session.get(Section, sec_id)
    sec.content = "changed"
    await db_session.flush()

    copy_sec = (
        await db_session.execute(select(Section).where(Section.document_id == copy_id))
    ).scalar_one()
    assert copy_sec.content == "x"


async def test_library_entry_model(db_session) -> None:
    """Smoke: таблица direction_program_library доступна."""
    from app.models import Direction, Profile

    direction = Direction(id=uuid.uuid4(), code=f"T{uuid.uuid4().hex[:6]}", name="Test")
    profile = Profile(id=uuid.uuid4(), direction_id=direction.id, name="Prof")
    doc = Document(id=uuid.uuid4(), filename="f.docx", doc_type="rp")
    db_session.add_all([direction, profile, doc])
    await db_session.flush()

    row = DirectionProgramLibrary(
        id=uuid.uuid4(),
        profile_id=profile.id,
        discipline_code="Б1.О.01",
        doc_kind="rpd",
        document_id=doc.id,
        content_hash="abc123",
        source_filename="f.docx",
    )
    db_session.add(row)
    await db_session.flush()

    found = (
        await db_session.execute(
            select(DirectionProgramLibrary).where(DirectionProgramLibrary.profile_id == profile.id)
        )
    ).scalar_one()
    assert found.discipline_code == "Б1.О.01"
