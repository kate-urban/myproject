"""Фильтрация служебных учебных планов из автотестов."""

from __future__ import annotations

import uuid

from app.models import Direction, Profile, StudyPlan
from app.utils.study_plan_filters import is_test_study_plan


def _plan(source_file: str, direction_code: str) -> StudyPlan:
    direction = Direction(code=direction_code, name="Test")
    profile = Profile(name="Profile", direction=direction)
    return StudyPlan(
        id=uuid.uuid4(),
        profile=profile,
        source_file=source_file,
        source_format="xml_upvo",
        form="ochnaya",
        year=2025,
    )


def test_is_test_study_plan_by_source_file() -> None:
    assert is_test_study_plan(_plan("test.plx", "05.03.06"))


def test_is_test_study_plan_by_direction_prefix() -> None:
    assert is_test_study_plan(_plan("real.plx", "99.99.abcd"))


def test_real_plan_is_not_test() -> None:
    assert not is_test_study_plan(_plan("B080301-LSTR-2026.plx", "08.03.01"))
