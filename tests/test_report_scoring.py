"""Тесты расчёта баллов отчёта 7.2."""

from __future__ import annotations

from uuid import uuid4

from app.models_tz import AuthorLoad
from app.services.report_scoring import UniquePointsTracker, points_for_author, split_author_loads


def test_unique_points_dedup_by_discipline_code() -> None:
    tracker = UniquePointsTracker()
    assert tracker.unique_for("Иванов И.И.", "B1.O.01", 20.0) == 20.0
    assert tracker.unique_for("Иванов И.И.", "B1.O.01", 20.0) == 0.0
    assert tracker.unique_for("Иванов И.И.", "B1.O.02", 15.0) == 15.0


def test_split_author_loads_respects_share() -> None:
    load_a = AuthorLoad(
        id=uuid4(),
        plan_discipline_id=uuid4(),
        author_name="А",
        share_percent=60,
    )
    load_b = AuthorLoad(
        id=uuid4(),
        plan_discipline_id=uuid4(),
        author_name="Б",
        share_percent=40,
    )
    splits = split_author_loads([load_a, load_b], [])
    assert len(splits) == 2
    assert abs(splits[0][2] - 60.0) < 0.01


def test_points_for_author_fixed() -> None:
    load = AuthorLoad(
        id=uuid4(),
        plan_discipline_id=uuid4(),
        author_name="А",
        fixed_points=80,
        share_percent=50,
    )
    _pp, pts = points_for_author(4.0, load, 50.0)
    assert pts == 40.0
