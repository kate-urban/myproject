"""Отчёты Excel по ТЗ (п. 7.1, 7.2)."""

from __future__ import annotations

import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.report_excel import build_author_rating_workbook, build_plan_summary_workbook

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/study-plans/{plan_id}/plan-summary.xlsx")
async def export_plan_summary_excel(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """Отчёт 7.1: свод по учебному плану (8 колонок, автор из РПД)."""
    try:
        wb = await build_plan_summary_workbook(db, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"plan_summary_{plan_id}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/study-plans/{plan_id}/author-rating.xlsx")
async def export_author_rating_excel(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """Отчёт 7.2: баллы разработки РПД (листы по авторам)."""
    try:
        wb = await build_author_rating_workbook(db, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="author_rating_{plan_id}.xlsx"'},
    )
