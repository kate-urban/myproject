"""Закрытие P2 и старт P3: справочники, structured, архив."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.models import Direction, PlanDiscipline, Profile, Program, StudyPlan
from app.models_tz import ArchiveVolume, RefDepartment, RefFgosCompetency
from app.services.archive_export import build_certification_text
from app.services.structured_program_sync import _literature_citations_from_html

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
    uid = uuid.uuid4().hex
    direction = Direction(
        code=kwargs.pop("direction_code", f"99.99.{uid[:4]}"),
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


def test_literature_citations_from_html_list() -> None:
    html = "<ul><li>Иванов И.И. Курс. — М., 2020.</li><li>Петров П.П. Учебник.</li></ul>"
    cites = _literature_citations_from_html(html)
    assert len(cites) == 2
    assert "Иванов" in cites[0]


def test_build_certification_text_uses_plan() -> None:
    plan = _mock_plan()
    volume = ArchiveVolume(
        id=uuid.uuid4(),
        study_plan_id=plan.id if plan.id else uuid.uuid4(),
        title="Том 2024",
        cover_text=None,
    )
    text = build_certification_text(volume, plan)
    assert "ЛИСТ-ЗАВЕРИТЕЛЬ" in text
    assert plan.profile.direction.code in text
    assert "2024" in text


@pytest.mark.asyncio
async def test_department_resolve_api(api_client: AsyncClient, db_session) -> None:
    code = f"T{uuid.uuid4().hex[:4]}"
    db_session.add(
        RefDepartment(
            id=uuid.uuid4(),
            code=code,
            name="Кафедра экологии",
        )
    )
    await db_session.commit()
    res = await api_client.get(f"/api/v1/reference/departments/resolve/?code={code}&year=2024")
    assert res.status_code == 200
    body = res.json()
    assert body["found"] is True
    assert "эколог" in body["name"].lower()


@pytest.mark.asyncio
async def test_fgos_check_api(api_client: AsyncClient, db_session) -> None:
    code = f"OPK-{uuid.uuid4().hex[:6]}"
    db_session.add(
        RefFgosCompetency(
            id=uuid.uuid4(),
            kind="OPK",
            code=code,
            title="Test competency",
        )
    )
    await db_session.commit()
    res = await api_client.get(f"/api/v1/reference/fgos/check/?competency={code}")
    assert res.status_code == 200
    assert res.json()["competency_ok"] is True


@pytest.mark.asyncio
async def test_archive_populate_replaces_items(api_client: AsyncClient, db_session) -> None:
    plan = _mock_plan(year=2025)
    disc = PlanDiscipline(
        study_plan=plan,
        code="Б1.О.01",
        name="Дисциплина",
        in_plan=True,
    )
    program = Program(discipline=disc)
    db_session.add(plan)
    await db_session.flush()
    volume = ArchiveVolume(
        study_plan_id=plan.id,
        title="Том",
        status="draft",
    )
    db_session.add(volume)
    await db_session.commit()

    res = await api_client.post(f"/api/v1/archive/volumes/{volume.id}/populate-from-plan/")
    assert res.status_code == 200
    assert res.json()["items"] == 1

    res2 = await api_client.post(f"/api/v1/archive/volumes/{volume.id}/populate-from-plan/")
    assert res2.status_code == 200
    assert res2.json()["items"] == 1

    detail = await api_client.get(f"/api/v1/archive/volumes/{volume.id}/")
    assert len(detail.json()["items"]) == 1


@pytest.mark.asyncio
async def test_certification_template_api(api_client: AsyncClient, db_session) -> None:
    plan = _mock_plan()
    db_session.add(plan)
    await db_session.commit()
    res = await api_client.get(
        f"/api/v1/archive/certification-template/?study_plan_id={plan.id}&title=Том+1"
    )
    assert res.status_code == 200
    assert "ЛИСТ-ЗАВЕРИТЕЛЬ" in res.json()["text"]
