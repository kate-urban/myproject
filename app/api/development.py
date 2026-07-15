"""Матрица разработки программ (сценарий 5 ТЗ)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import PlanDiscipline, Profile, Program, StudyPlan
from app.services.export_finalize import _current_academic_year_start
from app.services.rpd_extractor import RpdExtract
from app.services.validation.engine import validate_program
from app.services.validation.fos_engine import validate_program_fos
from app.services.validation.section_texts import load_section_texts_by_document

router = APIRouter(prefix="/development", tags=["development"])

_STATUS = {
    "no_rpd": {"code": "no_rpd", "label": "Нет РПД", "color": "#94a3b8"},
    "no_fos": {"code": "no_fos", "label": "Нет ФОС", "color": "#f59e0b"},
    "rpd_fail": {"code": "rpd_fail", "label": "Ошибки РПД", "color": "#dc2626"},
    "fos_fail": {"code": "fos_fail", "label": "Ошибки ФОС", "color": "#ea580c"},
    "ok": {"code": "ok", "label": "Готово", "color": "#059669"},
}

_REAPPROVAL_STATUS = {
    "needs_new_rpd": {"code": "needs_new_rpd", "label": "Нужна новая РПД", "color": "#dc2626"},
    "needs_amendment": {"code": "needs_amendment", "label": "Нужен лист изменений", "color": "#f59e0b"},
    "ok": {"code": "ok", "label": "Соответствует УП", "color": "#059669"},
    "no_rpd": {"code": "no_rpd", "label": "Нет РПД", "color": "#94a3b8"},
}


@router.get("/study-plans/{plan_id}/matrix/")
async def development_matrix(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    plan = await db.get(StudyPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    profile = await db.get(
        Profile,
        plan.profile_id,
        options=[selectinload(Profile.direction)],
    )
    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
            selectinload(PlanDiscipline.assessments),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    doc_ids = [
        d.program.document_id
        for d in disciplines
        if d.program and d.program.document_id
    ]
    section_map = await load_section_texts_by_document(db, doc_ids)

    items = []
    for d in disciplines:
        program = d.program
        if program is None or program.document_id is None:
            status = _STATUS["no_rpd"]
        else:
            try:
                texts = section_map.get(str(program.document_id))
                report = validate_program(
                    plan,
                    d,
                    program,
                    section_texts=texts,
                    plan_disciplines=disciplines,
                )
                if not report.passed:
                    status = _STATUS["rpd_fail"]
                elif program.fos_document_id is None:
                    status = _STATUS["no_fos"]
                else:
                    fos_report = validate_program_fos(plan, d, program)
                    status = _STATUS["ok"] if fos_report.passed else _STATUS["fos_fail"]
            except ValueError:
                status = _STATUS["rpd_fail"]

        items.append(
            {
                "discipline_id": str(d.id),
                "code": d.code,
                "name": d.name,
                "credits": d.credits,
                "status": status["code"],
                "status_label": status["label"],
                "color": status["color"],
                "has_rpd": bool(program and program.document_id),
                "has_fos": bool(program and program.fos_document_id),
            }
        )

    return {
        "study_plan_id": str(plan_id),
        "direction_code": profile.direction.code if profile else "",
        "profile_name": profile.name if profile else "",
        "items": items,
    }


@router.get("/study-plans/{plan_id}/reapproval-matrix/")
async def reapproval_matrix(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """Матрица переутверждения: соответствует УП / лист изменений / новая РПД."""
    plan = await db.get(StudyPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    profile = await db.get(
        Profile,
        plan.profile_id,
        options=[selectinload(Profile.direction)],
    )
    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program).selectinload(Program.amendments),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())
    current_year = _current_academic_year_start()
    items = []

    for discipline in disciplines:
        program = discipline.program
        if program is None or program.document_id is None:
            status = _REAPPROVAL_STATUS["no_rpd"]
        else:
            rpd = (
                RpdExtract.from_json(program.rpd_extract_json)
                if program.rpd_extract_json
                else None
            )
            amendments = list(program.amendments or [])
            years = set(rpd.reapproval_years if rpd else [])
            years.update(row.enrollment_year for row in amendments)

            if rpd and rpd.approval_year and plan.year and rpd.approval_year < plan.year - 3:
                status = _REAPPROVAL_STATUS["needs_new_rpd"]
            elif current_year not in years and not any(
                row.enrollment_year == current_year for row in amendments
            ):
                status = _REAPPROVAL_STATUS["needs_amendment"]
            else:
                status = _REAPPROVAL_STATUS["ok"]

        items.append(
            {
                "discipline_id": str(discipline.id),
                "program_id": str(program.id) if program else None,
                "code": discipline.code,
                "name": discipline.name,
                "status": status["code"],
                "status_label": status["label"],
                "color": status["color"],
            }
        )

    return {
        "study_plan_id": str(plan_id),
        "direction_code": profile.direction.code if profile else "",
        "profile_name": profile.name if profile else "",
        "current_academic_year": current_year,
        "items": items,
    }
