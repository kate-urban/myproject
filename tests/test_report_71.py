"""Тесты отчёта 7.1 (свод по УП)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import PlanDiscipline, Program
from app.models_tz import RefDepartment
from app.services.importers import StudyPlanImporter
from app.services.rpd_extractor import RpdExtract
from app.services.rpd_linker import _apply_rpd_extract

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


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_plan_summary_71_columns_and_authors(api_client: AsyncClient, db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    discipline = (
        await db_session.execute(
            select(PlanDiscipline).where(PlanDiscipline.study_plan_id == plan.id).limit(1)
        )
    ).scalar_one()
    db_session.add(
        RefDepartment(code=discipline.department_code or "55", name="Компьютерного моделирования")
    )

    program = Program(
        plan_discipline_id=discipline.id,
        status="uploaded",
    )
    rpd = RpdExtract(
        discipline_code=discipline.code,
        authors=["Курова Н.В.", "Киносто М.С."],
    )
    _apply_rpd_extract(program, rpd)
    db_session.add(program)
    discipline.program = program
    await db_session.commit()

    response = await api_client.get(f"/api/v1/reports/study-plans/{plan.id}/plan-summary.xlsx")
    assert response.status_code == 200

    wb = load_workbook(filename=io.BytesIO(response.content), read_only=True, data_only=True)
    ws = wb["Лист1"]
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    assert headers[:8] == [
        "Учебный план",
        "Направление подготовки",
        "Код кафедры",
        "Название кафедры",
        "Шифр дисциплины",
        "Наименование дисциплины",
        "Объем дисциплины в з.е.",
        "Автор",
    ]

    author_values = [row[7] for row in ws.iter_rows(min_row=2, values_only=True) if row[7]]
    assert any("Курова Н.В.\nКиносто М.С." in str(value) for value in author_values)

    dept_names = [row[3] for row in ws.iter_rows(min_row=2, values_only=True) if row[3]]
    assert "Компьютерного моделирования" in dept_names
