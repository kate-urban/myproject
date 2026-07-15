"""Привязка загруженного DOCX (РПД/ФОС) к дисциплине учебного плана."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PlanDiscipline, Program, StudyPlan
from app.services.fos_extractor import FosExtract, extract_fos
from app.services.rpd_extractor import RpdExtract, extract_rpd
from app.utils.discipline_code import code_from_filename, resolve_discipline_code


class ProgramLinkResult:
    def __init__(
        self,
        *,
        linked: bool,
        discipline_code: str | None = None,
        plan_discipline_id: uuid.UUID | None = None,
        study_plan_id: uuid.UUID | None = None,
        program_status: str | None = None,
        program_id: uuid.UUID | None = None,
        doc_kind: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.linked = linked
        self.discipline_code = discipline_code
        self.plan_discipline_id = plan_discipline_id
        self.study_plan_id = study_plan_id
        self.program_status = program_status
        self.program_id = program_id
        self.doc_kind = doc_kind
        self.reason = reason


def is_fos_filename(filename: str) -> bool:
    return Path(filename).stem.upper().startswith("FOS_")


def _apply_rpd_extract(program: Program, rpd: RpdExtract) -> None:
    program.rpd_discipline_code = rpd.discipline_code
    program.rpd_discipline_name = rpd.discipline_name
    program.rpd_direction_code = rpd.direction_code
    program.rpd_profile_name = rpd.profile_name
    program.rpd_department_code = rpd.department_code
    program.rpd_hours_total = rpd.hours_total
    program.rpd_credits = rpd.credits
    program.rpd_competencies = ";".join(rpd.competencies)
    program.rpd_extract_json = rpd.to_json()


def _apply_fos_extract(program: Program, fos: FosExtract) -> None:
    program.fos_extract_json = fos.to_json()


async def link_document_to_program(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    study_plan_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
) -> ProgramLinkResult:
    plan = await db.get(StudyPlan, study_plan_id)
    if plan is None:
        return ProgramLinkResult(linked=False, reason="study_plan_not_found")

    discipline_code = resolve_discipline_code(file_bytes, filename)
    if not discipline_code:
        return ProgramLinkResult(
            linked=False,
            study_plan_id=study_plan_id,
            reason="discipline_code_not_found",
        )

    result = await db.execute(
        select(PlanDiscipline)
        .options(selectinload(PlanDiscipline.program))
        .where(
            PlanDiscipline.study_plan_id == study_plan_id,
            PlanDiscipline.code == discipline_code,
        )
    )
    discipline = result.scalar_one_or_none()

    if discipline is None:
        alt_code = code_from_filename(filename)
        if alt_code and alt_code != discipline_code:
            result = await db.execute(
                select(PlanDiscipline)
                .options(selectinload(PlanDiscipline.program))
                .where(
                    PlanDiscipline.study_plan_id == study_plan_id,
                    PlanDiscipline.code == alt_code,
                )
            )
            discipline = result.scalar_one_or_none()
            if discipline is not None:
                discipline_code = alt_code

    if discipline is None:
        return ProgramLinkResult(
            linked=False,
            discipline_code=discipline_code,
            study_plan_id=study_plan_id,
            reason="discipline_not_in_plan",
        )

    program = discipline.program
    doc_kind = "fos" if is_fos_filename(filename) else "rpd"

    if program is None:
        program = Program(
            id=uuid.uuid4(),
            plan_discipline_id=discipline.id,
            document_id=None if doc_kind == "fos" else document_id,
            fos_document_id=document_id if doc_kind == "fos" else None,
            status="uploaded",
        )
        db.add(program)
    elif doc_kind == "fos":
        program.fos_document_id = document_id
        program.status = "uploaded"
    else:
        program.document_id = document_id
        program.status = "uploaded"

    if doc_kind == "fos":
        _apply_fos_extract(program, extract_fos(file_bytes, filename))
    else:
        rpd = extract_rpd(file_bytes, filename)
        _apply_rpd_extract(program, rpd)
        from app.services.structured_program_sync import sync_program_from_extract

        await sync_program_from_extract(db, program, rpd, discipline=discipline)

    return ProgramLinkResult(
        linked=True,
        discipline_code=discipline_code,
        plan_discipline_id=discipline.id,
        study_plan_id=study_plan_id,
        program_id=program.id,
        program_status="uploaded",
        doc_kind=doc_kind,
    )
