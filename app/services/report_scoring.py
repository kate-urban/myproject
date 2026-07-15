"""Улучшенный расчёт баллов для отчёта 7.2."""

from __future__ import annotations

from uuid import UUID

from app.models_tz import AuthorLoad


def split_author_loads(
    loads: list[AuthorLoad],
    rpd_authors: list[str],
) -> list[tuple[str, AuthorLoad | None, float]]:
    """(имя, нагрузка, доля %) — без теневых в колонке преподаватель."""
    visible = [load for load in loads if load.author_name.strip() and not load.is_shadow]
    if visible:
        if any(load.share_percent is not None for load in visible):
            total_share = sum(float(load.share_percent or 0) for load in visible) or 100.0
            return [
                (load.author_name.strip(), load, float(load.share_percent or 0) / total_share * 100.0)
                for load in visible
            ]
        share = 100.0 / len(visible)
        return [(load.author_name.strip(), load, share) for load in visible]
    if rpd_authors:
        share = 100.0 / len(rpd_authors)
        return [(name, None, share) for name in rpd_authors]
    return []


def points_for_author(
    credits: float,
    load: AuthorLoad | None,
    share_percent: float,
) -> tuple[float, float]:
    points_per = float(load.points_per_credit if load and load.points_per_credit else 20)
    if load and load.fixed_points is not None:
        total = float(load.fixed_points)
    else:
        total = credits * points_per
    return points_per, round(total * share_percent / 100.0, 2)


class UniquePointsTracker:
    """«Баллы без повторов» — одна дисциплина (шифр) на автора один раз."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def unique_for(self, author: str, discipline_code: str, per_author_points: float) -> float:
        key = (author.strip().lower(), discipline_code.strip().upper())
        if key in self._seen:
            return 0.0
        self._seen.add(key)
        return per_author_points
