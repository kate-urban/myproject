"""Тесты ИИ-помощника методиста."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth_deps import get_current_user
from app.database import get_db
from app.main import app
from app.services.ai_assistant import build_fallback_answer, html_to_plain
from app.services.auth import CurrentUser


def test_html_to_plain_strips_tags() -> None:
    text = html_to_plain("<p>Лекции <strong>37</strong></p><table><tr><td>13</td></tr></table>")
    assert "Лекции" in text
    assert "37" in text
    assert "13" in text
    assert "<p>" not in text


def test_fallback_r025_mentions_table_13() -> None:
    answer = build_fallback_answer(
        question="Объясни",
        rule_id="R025",
        kind="rpd",
        discipline_code="Б1.О.11",
        rule_name="Контакт: лек+практ+лаб",
        message="Сумма не совпадает",
        expected="108",
        actual="37",
        section_title="1.3 Объём дисциплины",
        section_snippet="<p>Контактная работа 37</p>",
    )
    assert "R025" in answer
    assert "1.3" in answer
    assert "108" in answer
    assert "37" in answer
    assert "3.3" in answer or "Не предусмотрены" in answer


@pytest.mark.integration
@pytest.mark.asyncio
async def test_assist_validation_api_local(db_session, monkeypatch) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)

    async def _override_db():
        yield db_session

    async def _fake_user() -> CurrentUser:
        return CurrentUser(
            id=uuid.uuid4(),
            username="tester",
            display_name="Tester",
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _fake_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/assist/validation/",
            json={
                "question": "Объясни ошибку",
                "rule_id": "R022",
                "kind": "rpd",
                "discipline_code": "Б1.О.08",
                "expected": "110",
                "actual": "36",
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local"
    assert "R022" in payload["answer"]
    assert "110" in payload["answer"]
