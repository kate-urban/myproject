"""HTTP-тесты ключевых API (ASGI + PostgreSQL)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
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


@pytest.mark.asyncio
async def test_ui_routes(api_client: AsyncClient) -> None:
    workspace = await api_client.get("/")
    assert workspace.status_code == 200
    assert "workspace" in workspace.text.lower() or "syllabus" in workspace.text.lower()

    validation = await api_client.get("/validation")
    assert validation.status_code == 200
    assert "shell.js" in validation.text
    assert "appRibbon" in validation.text
    assert "validation_structured.js" in validation.text


@pytest.mark.asyncio
async def test_system_info(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/system/info/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_ui"] == "/validation"
    assert payload["workspace_ui"] == "/"


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_study_plan_import_and_list(api_client: AsyncClient, db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    await db_session.commit()

    listed = await api_client.get("/api/v1/study-plans/")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert str(plan.id) in ids

    detail = await api_client.get(f"/api/v1/study-plans/{plan.id}/")
    assert detail.status_code == 200
    assert detail.json()["direction_code"] == "54.04.01"


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_disciplines_and_validate_endpoints(api_client: AsyncClient, db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    await db_session.commit()

    disciplines = await api_client.get(f"/api/v1/study-plans/{plan.id}/disciplines/")
    assert disciplines.status_code == 200
    items = disciplines.json()
    assert len(items) >= 1
    assert any(item["code"] == "Б1.О.01.07" for item in items)

    validate = await api_client.get(f"/api/v1/study-plans/{plan.id}/validate/?rule_ids=R001")
    assert validate.status_code == 200
    body = validate.json()
    assert body["study_plan_id"] == str(plan.id)
    assert body["checked"] >= 0


@pytest.mark.asyncio
async def test_navigation_tree(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/study-plans/navigation-tree/")
    assert response.status_code == 200
    payload = response.json()
    assert "tree" in payload
    assert "root" in payload
