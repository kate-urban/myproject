"""Тесты фундамента ТЗ: справочники, матрица, частичный экспорт."""

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
async def test_reference_abbreviations_seeded(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/reference/abbreviations/")
    assert response.status_code == 200
    items = response.json()
    assert any(item["pattern"] == "ОПР-1" and item["replacement"] == "ОПР" for item in items)


@pytest.mark.asyncio
async def test_phrases_crud(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/reference/phrases/",
        json={"category": "test", "text": "Тестовая фраза", "version": 1},
    )
    assert created.status_code == 200
    phrase_id = created.json()["id"]

    listed = await api_client.get("/api/v1/reference/phrases/?category=test")
    assert listed.status_code == 200
    assert any(p["id"] == phrase_id for p in listed.json())

    updated = await api_client.put(
        f"/api/v1/reference/phrases/{phrase_id}/",
        json={"text": "Обновлённая фраза"},
    )
    assert updated.status_code == 200

    deleted = await api_client.delete(f"/api/v1/reference/phrases/{phrase_id}/")
    assert deleted.status_code == 200


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="M540401-2026.plx missing")
@pytest.mark.asyncio
async def test_development_matrix(api_client: AsyncClient, db_session) -> None:
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    await db_session.commit()

    response = await api_client.get(f"/api/v1/development/study-plans/{plan.id}/matrix/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["study_plan_id"] == str(plan.id)
    assert isinstance(payload["items"], list)
    assert len(payload["items"]) >= 1


@pytest.mark.asyncio
async def test_archive_volume_crud(api_client: AsyncClient, db_session) -> None:
    if not DESIGN_PLX.is_file():
        pytest.skip("M540401-2026.plx missing")
    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    await db_session.commit()

    created = await api_client.post(
        "/api/v1/archive/volumes/",
        json={"study_plan_id": str(plan.id), "title": "Том 1"},
    )
    assert created.status_code == 200
    volume_id = created.json()["id"]

    listed = await api_client.get(f"/api/v1/archive/volumes/?study_plan_id={plan.id}")
    assert listed.status_code == 200
    assert any(v["id"] == volume_id for v in listed.json())
