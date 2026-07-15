"""HTTP-тесты CRUD topics / zuv / literature (ТЗ P2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import PlanDiscipline, Program
from app.services.importers import StudyPlanImporter

DESIGN_PLX = Path(__file__).resolve().parents[1] / "samples" / "M540401-2026.plx"

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


@pytest.fixture
async def program_id(db_session) -> str:
    if not DESIGN_PLX.is_file():
        pytest.skip("M540401-2026.plx missing")

    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    discipline = (
        await db_session.execute(
            select(PlanDiscipline).where(PlanDiscipline.study_plan_id == plan.id).limit(1)
        )
    ).scalar_one()
    program = Program(plan_discipline_id=discipline.id, status="uploaded")
    db_session.add(program)
    discipline.program = program
    await db_session.commit()
    return str(program.id)


@pytest.mark.asyncio
async def test_program_structured_empty(api_client: AsyncClient, program_id: str) -> None:
    response = await api_client.get(f"/api/v1/programs/{program_id}/structured/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["program_id"] == program_id
    assert payload["topics"] == []
    assert payload["zuv"] == []
    assert payload["literature"] == []


@pytest.mark.asyncio
async def test_program_topics_crud(api_client: AsyncClient, program_id: str) -> None:
    put = await api_client.put(
        f"/api/v1/programs/{program_id}/topics/",
        json={
            "items": [
                {
                    "topic_number": "1",
                    "title": "Введение",
                    "semester": 1,
                    "hours_lecture": 4,
                    "hours_practical": 2,
                },
                {"topic_number": "2", "title": "Основы", "semester": 2},
            ]
        },
    )
    assert put.status_code == 200
    items = put.json()["items"]
    assert len(items) == 2
    assert items[0]["title"] == "Введение"

    get = await api_client.get(f"/api/v1/programs/{program_id}/topics/")
    assert get.status_code == 200
    assert len(get.json()) == 2

    structured = await api_client.get(f"/api/v1/programs/{program_id}/structured/")
    assert len(structured.json()["topics"]) == 2


@pytest.mark.asyncio
async def test_program_zuv_and_literature_crud(api_client: AsyncClient, program_id: str) -> None:
    zuv = await api_client.put(
        f"/api/v1/programs/{program_id}/zuv/",
        json={
            "items": [
                {
                    "indicator_code": "ОПК-1",
                    "zuv_type": "know",
                    "text": "Знает основы",
                    "topic_ref": "1",
                }
            ]
        },
    )
    assert zuv.status_code == 200
    assert zuv.json()["items"][0]["indicator_code"] == "ОПК-1"

    lit = await api_client.put(
        f"/api/v1/programs/{program_id}/literature/",
        json={
            "items": [
                {"citation": "Иванов И.И. Учебник.", "lit_type": "main"},
            ]
        },
    )
    assert lit.status_code == 200
    assert "Учебник" in lit.json()["items"][0]["citation"]

    structured = await api_client.get(f"/api/v1/programs/{program_id}/structured/")
    body = structured.json()
    assert len(body["zuv"]) == 1
    assert len(body["literature"]) == 1


@pytest.mark.asyncio
async def test_program_structured_not_found(api_client: AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000001"
    response = await api_client.get(f"/api/v1/programs/{missing}/structured/")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_program_structured_refresh_requires_document(
    api_client: AsyncClient, program_id: str
) -> None:
    response = await api_client.post(
        f"/api/v1/programs/{program_id}/structured/refresh-from-document/"
    )
    assert response.status_code == 422
    assert "документ" in response.json()["detail"].lower()
