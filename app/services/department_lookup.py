"""Поиск названия кафедры по коду из справочника ref_departments."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tz import RefDepartment


async def resolve_department_name(
    db: AsyncSession,
    code: str | None,
    *,
    enrollment_year: int | None = None,
) -> str:
    if not code or not str(code).strip():
        return ""
    normalized = str(code).strip()
    query = select(RefDepartment.name, RefDepartment.opened_on, RefDepartment.closed_on).where(
        RefDepartment.code == normalized
    )
    result = await db.execute(query.order_by(RefDepartment.opened_on.desc().nullslast()))
    rows = result.all()
    if not rows:
        return ""

    if enrollment_year is not None:
        from datetime import date

        ref = date(enrollment_year, 9, 1)
        for name, opened_on, closed_on in rows:
            if opened_on and opened_on > ref:
                continue
            if closed_on and closed_on < ref:
                continue
            return name

    return rows[0][0]


async def department_names_by_codes(
    db: AsyncSession,
    codes: set[str],
    *,
    enrollment_year: int | None = None,
) -> dict[str, str]:
    if not codes:
        return {}
    mapping: dict[str, str] = {}
    for code in sorted(codes):
        mapping[code] = await resolve_department_name(
            db, code, enrollment_year=enrollment_year
        )
    return mapping
