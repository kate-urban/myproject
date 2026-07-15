"""Фильтрация служебных учебных планов из pytest/интеграционных тестов."""

from __future__ import annotations

from app.models import Direction, Profile, StudyPlan

_TEST_SOURCE_FILES = frozenset({"test.plx"})
_TEST_DIRECTION_PREFIX = "99.99."


def is_test_study_plan(
    plan: StudyPlan,
    *,
    direction_code: str | None = None,
) -> bool:
    """True для планов, созданных автотестами (не показываем в UI)."""
    source = (plan.source_file or "").strip().lower()
    if source in _TEST_SOURCE_FILES:
        return True
    code = direction_code
    if code is None and plan.profile is not None and plan.profile.direction is not None:
        code = plan.profile.direction.code
    return bool(code and code.startswith(_TEST_DIRECTION_PREFIX))


def is_test_direction(direction: Direction | None) -> bool:
    if direction is None:
        return False
    return direction.code.startswith(_TEST_DIRECTION_PREFIX)
