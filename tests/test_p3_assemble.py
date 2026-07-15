"""Тесты P3: МТО, аннотация, архив."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.models import Direction, PlanDiscipline, Profile, Program, StudyPlan
from app.models_tz import ArchiveVolume, ArchiveVolumeItem, RefMtoRoom, RefPhrase
from app.services.archive_export import build_inventory_text
from app.services.p3_assemble import build_annotation_suggestion, format_mto_text

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client(db_session):
    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _mock_plan(**kwargs) -> StudyPlan:
    uid = uuid.uuid4().hex[:6]
    direction = Direction(
        code=kwargs.pop("direction_code", f"99.99.{uid[:2]}"),
        name=kwargs.pop("direction_name", "Test direction"),
    )
    profile = Profile(name=kwargs.pop("profile_name", "Test profile"), direction=direction)
    defaults = {
        "profile": profile,
        "source_file": "test.plx",
        "source_format": "xml_upvo",
        "form": "ochnaya",
        "year": 2024,
    }
    defaults.update(kwargs)
    return StudyPlan(**defaults)


def test_format_mto_text_lists_rooms() -> None:
    rooms = [
        RefMtoRoom(code="A-101", name="Лекционная", equipment="Проектор", building="Корпус 1"),
    ]
    text = format_mto_text("Вводная фраза.", rooms)
    assert "A-101" in text
    assert "Проектор" in text
    assert text.startswith("Вводная фраза.")


def test_build_inventory_text_includes_page_range() -> None:
    volume = ArchiveVolume(
        id=uuid.uuid4(),
        study_plan_id=uuid.uuid4(),
        title="Том 1",
    )
    program_id = uuid.uuid4()
    disc_id = uuid.uuid4()
    program = Program(id=program_id, plan_discipline_id=disc_id)
    item = ArchiveVolumeItem(
        id=uuid.uuid4(),
        volume_id=volume.id,
        program_id=program_id,
        row_order=0,
        sheet_count=5,
        page_start=3,
        page_end=7,
    )
    disciplines = {disc_id: PlanDiscipline(id=disc_id, code="Б1.О.01", name="Экология")}
    text = build_inventory_text(volume, [item], disciplines, {program_id: program})
    assert "3–7" in text
    assert "Б1.О.01" in text


@pytest.mark.asyncio
async def test_annotation_suggestion_uses_phrase(db_session) -> None:
    plan = _mock_plan()
    disc = PlanDiscipline(
        study_plan=plan,
        code="Б1.О.01",
        name="Экология",
        credits=3.0,
        in_plan=True,
    )
    program = Program(discipline=disc, program_kind="discipline")
    db_session.add(
        RefPhrase(
            id=uuid.uuid4(),
            category="discipline_annotation",
            version=1,
            text="Дисциплина «{discipline_name}» — {credits} з.е.",
            is_active=True,
        )
    )
    db_session.add(plan)
    await db_session.flush()
    text = await build_annotation_suggestion(db_session, program, disc, plan)
    assert "Экология" in text
    assert "3" in text


@pytest.mark.asyncio
async def test_mto_rooms_and_apply_constructor(api_client: AsyncClient, db_session) -> None:
    plan = _mock_plan()
    disc = PlanDiscipline(
        study_plan=plan,
        code="Б2.О.01",
        name="Учебная практика",
        in_plan=True,
        object_type="P",
    )
    program = Program(
        discipline=disc,
        program_kind="practice",
        constructor_json='{"mto_text":"","annotation":""}',
    )
    room = RefMtoRoom(
        id=uuid.uuid4(),
        code=f"R{uuid.uuid4().hex[:4]}",
        name="Аудитория",
        equipment="Стенды",
    )
    db_session.add(plan)
    db_session.add(room)
    await db_session.commit()

    put = await api_client.put(
        f"/api/v1/programs/{program.id}/mto/rooms/",
        json={"room_ids": [str(room.id)]},
    )
    assert put.status_code == 200

    suggest = await api_client.get(f"/api/v1/programs/{program.id}/mto/suggest/")
    assert suggest.status_code == 200
    assert room.code in suggest.json()["text"]

    apply_res = await api_client.post(f"/api/v1/programs/{program.id}/mto/apply/", json={})
    assert apply_res.status_code == 200
    assert apply_res.json()["target"] == "constructor"

    annot = await api_client.post(f"/api/v1/programs/{program.id}/annotation/apply/", json={})
    assert annot.status_code == 200
    assert annot.json()["target"] == "constructor"
