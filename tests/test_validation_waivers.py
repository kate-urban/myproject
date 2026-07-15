"""Тесты ручного снятия ошибок сверки."""

from __future__ import annotations

from app.services.validation.rules import RuleResult
from app.services.validation.waivers import apply_waivers


def _failed_rule(rule_id: str = "R001") -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name="Test",
        passed=False,
        message="ошибка",
        severity="critical",
    )


def test_apply_waivers_marks_failed_as_passed():
    results = [_failed_rule("R001"), _failed_rule("R002")]
    updated = apply_waivers(results, {"R001"})
    assert updated[0].passed is True
    assert updated[0].waived is True
    assert updated[1].passed is False
    assert updated[1].waived is False


def test_apply_waivers_does_not_touch_passed_rules():
    passed = RuleResult(
        rule_id="R003",
        name="OK",
        passed=True,
        message="ok",
        severity="critical",
    )
    updated = apply_waivers([passed], {"R003"})
    assert updated[0].passed is True
    assert updated[0].waived is False


def test_apply_waivers_empty_set_is_noop():
    results = [_failed_rule()]
    assert apply_waivers(results, set()) is results
    assert apply_waivers(results, None) is results
