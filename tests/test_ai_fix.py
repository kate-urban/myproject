"""Тесты LLM-правок сверки (без реального API)."""

from __future__ import annotations

import pytest

from app.services.ai_fix import (
    _coerce_changes,
    _parse_llm_json,
    _verify_changes,
    apply_changes_to_html,
)
from app.services.validation.rules import RuleResult
from app.services.validation_fix import FixChange


def test_parse_llm_json_from_fence() -> None:
    raw = '```json\n{"explanation": "test", "changes": []}\n```'
    data = _parse_llm_json(raw)
    assert data["explanation"] == "test"


def test_coerce_changes_skips_invalid() -> None:
    changes = _coerce_changes([
        {"field": "hours", "old": "36", "new": "110", "row_label": "Контакт"},
        {"field": "x", "old": "", "new": "1"},
        {"old": "a", "new": "a"},
    ])
    assert len(changes) == 1
    assert changes[0].new == "110"


def test_apply_changes_to_html() -> None:
    html = "<p>Контактная работа: 36 ч</p>"
    changes = [FixChange(field="contact", old="36", new="110", row_label="Контакт")]
    patched, applied = apply_changes_to_html(html, changes)
    assert patched == "<p>Контактная работа: 110 ч</p>"
    assert len(applied) == 1


def test_verify_changes_marks_safe_when_new_matches_expected() -> None:
    rule = RuleResult(
        rule_id="R022",
        name="test",
        passed=False,
        message="расхождение",
        expected="110",
        actual="36",
    )
    changes = [FixChange(field="contact", old="36", new="110", row_label="Контакт")]
    verified, apply_safe = _verify_changes(changes, rule)
    assert len(verified) == 1
    assert apply_safe is True


def test_verify_changes_not_safe_when_new_differs() -> None:
    rule = RuleResult(
        rule_id="R018",
        name="test",
        passed=False,
        message="расхождение",
        expected="37",
        actual="13",
    )
    changes = [FixChange(field="q1", old="2", new="5", row_label="1.1")]
    _verified, apply_safe = _verify_changes(changes, rule)
    assert apply_safe is False


@pytest.mark.asyncio
async def test_suggest_llm_validation_fix_applies_mock_response(monkeypatch) -> None:
    from app.models import PlanDiscipline
    from app.services.ai_fix import suggest_llm_validation_fix
    from app.services.rpd_extractor import RpdExtract
    from app.services.validation.rules import ValidationContext

    llm_payload = {
        "explanation": "Заменить контактные часы на эталон УП",
        "changes": [
            {
                "field": "contact_hours",
                "row_label": "Контактная работа",
                "old": "36",
                "new": "110",
            }
        ],
    }

    async def _fake_llm(_prompt: str) -> dict:
        return llm_payload

    monkeypatch.setattr("app.services.ai_fix.ask_llm_fix", _fake_llm)

    discipline = PlanDiscipline(code="Б1.О.08", name="Математика", hours_total=396, credits=11)
    ctx = ValidationContext(
        discipline=discipline,
        direction_code="05.03.06",
        direction_name="Экология",
        profile_name="Экология",
        rpd=RpdExtract(discipline_code="Б1.О.08"),
    )
    rule = RuleResult(
        rule_id="R022",
        name="Контакт",
        passed=False,
        message="расхождение",
        expected="110",
        actual="36",
    )
    html = "<table><tr><td>Контактная работа</td><td>36</td></tr></table>"

    result = await suggest_llm_validation_fix(
        "R022",
        html,
        ctx,
        rule,
        discipline_code="Б1.О.08",
    )

    assert result.supported is True
    assert result.source == "llm"
    assert result.apply_safe is True
    assert "110" in (result.patched_html or "")
    assert len(result.changes) == 1
