"""API переутверждения программ (ТЗ сценарий 2)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import PlanDiscipline, Profile, Program, StudyPlan
from app.models_tz import ProgramAmendment
from app.services.department_lookup import department_names_by_codes
from app.services.pdf_export import load_active_signatures
from app.services.reapproval_export import ReapprovalSignature, build_reapproval_pdf_bytes
from app.services.rpd_extractor import RpdExtract
from app.utils.http import attachment_disposition

router = APIRouter(prefix="/programs", tags=["reapproval"])


class AmendmentIn(BaseModel):
    enrollment_year: int
    amendment_kind: str = "none"  # none | sheet | full_rewrite
    protocol_ref: str | None = None
    change_summary: str | None = None
    approved_on: date | None = None


@router.get("/{program_id}/amendments/")
async def list_amendments(program_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProgramAmendment)
        .where(ProgramAmendment.program_id == program_id)
        .order_by(ProgramAmendment.enrollment_year)
    )
    return [
        {
            "id": str(row.id),
            "enrollment_year": row.enrollment_year,
            "amendment_kind": row.amendment_kind,
            "protocol_ref": row.protocol_ref,
            "change_summary": row.change_summary,
            "approved_on": row.approved_on.isoformat() if row.approved_on else None,
        }
        for row in result.scalars().all()
    ]


@router.post("/{program_id}/amendments/")
async def create_amendment(
    program_id: UUID,
    body: AmendmentIn,
    db: AsyncSession = Depends(get_db),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Программа не найдена")

    row = ProgramAmendment(
        program_id=program_id,
        enrollment_year=body.enrollment_year,
        amendment_kind=body.amendment_kind,
        protocol_ref=body.protocol_ref,
        change_summary=body.change_summary,
        approved_on=body.approved_on,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": str(row.id),
        "enrollment_year": row.enrollment_year,
        "amendment_kind": row.amendment_kind,
        "protocol_ref": row.protocol_ref,
        "change_summary": row.change_summary,
        "approved_on": row.approved_on.isoformat() if row.approved_on else None,
    }


@router.delete("/{program_id}/amendments/{amendment_id}/")
async def delete_amendment(
    program_id: UUID,
    amendment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(ProgramAmendment, amendment_id)
    if row is None or row.program_id != program_id:
        raise HTTPException(status_code=404, detail="Запись переутверждения не найдена")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/{program_id}/reapproval.pdf")
async def export_reapproval_pdf(
    program_id: UUID,
    variant: str = Query("simple", pattern="^(empty|simple|transition|auto)$"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Program)
        .options(
            selectinload(Program.discipline).selectinload(PlanDiscipline.study_plan),
            selectinload(Program.amendments),
        )
        .where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None or program.discipline is None:
        raise HTTPException(status_code=404, detail="Программа не найдена")

    discipline = program.discipline
    plan = discipline.study_plan
    profile = await db.get(
        Profile,
        plan.profile_id,
        options=[selectinload(Profile.direction)],
    ) if plan else None

    rpd = RpdExtract.from_json(program.rpd_extract_json) if program.rpd_extract_json else None
    amendments = list(program.amendments or [])
    resolved_variant = variant
    if variant == "auto":
        if not amendments:
            resolved_variant = "empty"
        elif len(amendments) >= 2:
            resolved_variant = "transition"
        elif amendments[0].amendment_kind == "none":
            resolved_variant = "simple"
        else:
            resolved_variant = "transition"

    direction_label = ""
    if profile and profile.direction:
        direction_label = f"{profile.direction.code} {profile.direction.name}, профиль «{profile.name}»"

    department_name = ""
    if discipline.department_code and plan:
        dept_names = await department_names_by_codes(
            db, {discipline.department_code}, enrollment_year=plan.year
        )
        department_name = dept_names.get(discipline.department_code, "")

    signatures = await load_active_signatures(db)
    dept_head = next(
        (sig for sig in signatures if sig.role in ("dept_head", "discipline_head")),
        None,
    )
    signature = ReapprovalSignature(
        full_name=dept_head.full_name if dept_head else "",
        png_path=dept_head.png_path if dept_head else None,
    )

    pdf_bytes = build_reapproval_pdf_bytes(
        variant=resolved_variant,
        discipline_code=discipline.code,
        discipline_name=discipline.name,
        amendments=amendments,
        enrollment_year=plan.year if plan else None,
        direction_label=direction_label,
        reapproval_years=rpd.reapproval_years if rpd else None,
        department_name=department_name,
        signature=signature,
    )
    filename = f"reapproval_{discipline.code}_{resolved_variant}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=attachment_disposition(filename),
    )
