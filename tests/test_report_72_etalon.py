"""Сверка структуры отчёта 7.2 с эталоном Excel."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import PlanDiscipline, Program
from app.models_tz import AuthorLoad, RefDepartment
from app.services.importers import StudyPlanImporter
from app.services.report_excel import build_author_rating_workbook
from app.services.rpd_extractor import RpdExtract
from app.services.rpd_linker import _apply_rpd_extract

DESIGN_PLX = Path(__file__).resolve().parents[1] / "samples" / "M540401-2026.plx"
ETALON_XLSX = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "Информационные материалы"
    / "Otchet_po_razrabotke_RPd_2025_1.xlsx"
)

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


def _normalize_formula(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("="):
        return ""
    text = value.replace(" ", "").upper()
    text = re.sub(r"\$\d+", "N", text)
    text = re.sub(r"[A-Z]+\d+", "CELL", text)
    return text


def _structure_checks(generated, etalon) -> tuple[int, int]:
    passed = 0
    total = 0

    def check(condition: bool) -> None:
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1

    for name in ("Справочник", "Преподаватели", "Сводная баллов", "Свод"):
        check(name in generated.sheetnames and name in etalon.sheetnames)

    g_ref = generated["Справочник"]
    e_ref = etalon["Справочник"]
    check(g_ref.cell(1, 1).value == e_ref.cell(1, 1).value == "Номер")
    check(g_ref.cell(1, 2).value == e_ref.cell(1, 2).value == "Название кафедры")

    g_svod = generated["Свод"]
    e_svod = etalon["Свод"]
    for col in range(1, 8):
        check(g_svod.cell(6, col).value == e_svod.cell(6, col).value)

    g_teach = generated["Преподаватели"]
    e_teach = etalon["Преподаватели"]
    check(g_teach.cell(1, 3).value == e_teach.cell(1, 3).value == "Ф.И.О.")
    check(g_teach.cell(1, 4).value == e_teach.cell(1, 4).value == "Свод")
    check(g_teach.cell(1, 9).value == e_teach.cell(1, 9).value == "Баллы")

    author_sheets = [name for name in generated.sheetnames if name not in ("Справочник", "Преподаватели", "Сводная баллов", "Свод")]
    etalon_author_sheets = [
        name for name in etalon.sheetnames if name not in ("Справочник", "Преподаватели", "Сводная баллов", "Свод")
    ]
    check(len(author_sheets) >= 1 and len(etalon_author_sheets) >= 1)

    if author_sheets and etalon_author_sheets:
        g_author = generated[author_sheets[0]]
        e_author = etalon[etalon_author_sheets[0]]
        check(g_author.cell(1, 1).value == e_author.cell(1, 1).value == "Ф.И.О.:")
        check(g_author.cell(3, 1).value == e_author.cell(3, 1).value == "Итого")
        for col in range(1, 11):
            check(g_author.cell(4, col).value == e_author.cell(4, col).value)

        for col in (7, 9, 10):
            formula = g_author.cell(5, col).value
            check(isinstance(formula, str) and formula.startswith("="))

        for col in (4, 5, 6, 8, 9, 10):
            g_formula = _normalize_formula(g_teach.cell(2, col).value)
            e_formula = _normalize_formula(e_teach.cell(2, col).value)
            check(bool(g_formula) and g_formula == e_formula)

        g_totals = generated["Сводная баллов"]
        e_totals = etalon["Сводная баллов"]
        check(g_totals.cell(1, 3).value == e_totals.cell(1, 3).value == "Ф.И.О.")
        check(str(generated["Сводная баллов"].cell(2, 4).value).startswith("=Преподаватели!"))

    return passed, total


@pytest.mark.skipif(not ETALON_XLSX.is_file(), reason="etalon 7.2 xlsx missing")
def test_etalon_workbook_readable() -> None:
    etalon = load_workbook(ETALON_XLSX, read_only=False, data_only=False)
    assert etalon.sheetnames[:4] == ["Справочник", "Преподаватели", "Сводная баллов", "Свод"]


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.skipif(not ETALON_XLSX.is_file(), reason="etalon 7.2 xlsx missing")
@pytest.mark.asyncio
async def test_author_rating_72_matches_etalon_structure(db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)

    disciplines = (
        await db_session.execute(
            select(PlanDiscipline).where(PlanDiscipline.study_plan_id == plan.id).limit(3)
        )
    ).scalars().all()

    for discipline in disciplines:
        db_session.add(
            RefDepartment(code=discipline.department_code or "55", name="Тестовая кафедра")
        )
        program = Program(plan_discipline_id=discipline.id, status="uploaded")
        rpd = RpdExtract(
            discipline_code=discipline.code,
            authors=["Иванов И.И.", "Петров П.П."],
        )
        _apply_rpd_extract(program, rpd)
        db_session.add(program)
        discipline.program = program
        db_session.add(
            AuthorLoad(
                plan_discipline_id=discipline.id,
                author_name="Иванов И.И.",
                share_percent=60,
                points_per_credit=20,
            )
        )
        db_session.add(
            AuthorLoad(
                plan_discipline_id=discipline.id,
                author_name="Петров П.П.",
                share_percent=40,
                points_per_credit=20,
            )
        )
    await db_session.commit()

    wb = await build_author_rating_workbook(db_session, plan.id)
    buf = io.BytesIO()
    wb.save(buf)
    generated = load_workbook(io.BytesIO(buf.getvalue()), read_only=False, data_only=False)
    etalon = load_workbook(ETALON_XLSX, read_only=False, data_only=False)

    passed, total = _structure_checks(generated, etalon)
    score = passed / total if total else 0.0
    assert score >= 0.9, f"structure match {score:.0%} ({passed}/{total})"


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_author_rating_72_api_download(api_client: AsyncClient, db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    response = await api_client.get(f"/api/v1/reports/study-plans/{plan.id}/author-rating.xlsx")
    assert response.status_code == 200
    wb = load_workbook(filename=io.BytesIO(response.content), read_only=True, data_only=True)
    assert wb.sheetnames[:4] == ["Справочник", "Преподаватели", "Сводная баллов", "Свод"]
