"""Привязка загруженного DOCX (РПД/ФОС) к дисциплине учебного плана."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PlanDiscipline, Program, StudyPlan
from app.services.direction_library import (
    PropagateResult,
    attach_document_to_discipline,
    doc_kind_from_filename,
    link_and_propagate_document,
)
from app.services.fos_extractor import FosExtract, extract_fos
from app.services.rpd_extractor import RpdExtract, extract_rpd, extract_rpd_from_pdf
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
        propagated_plans: int = 0,
        reused_document: bool = False,
    ) -> None:
        self.linked = linked
        self.discipline_code = discipline_code
        self.plan_discipline_id = plan_discipline_id
        self.study_plan_id = study_plan_id
        self.program_status = program_status
        self.program_id = program_id
        self.doc_kind = doc_kind
        self.reason = reason
        self.propagated_plans = propagated_plans
        self.reused_document = reused_document

    @classmethod
    def from_propagate(cls, result: PropagateResult) -> ProgramLinkResult:
        return cls(
            linked=result.linked,
            discipline_code=result.discipline_code,
            plan_discipline_id=result.plan_discipline_id,
            study_plan_id=result.study_plan_id,
            program_id=result.program_id,
            program_status=result.program_status,
            doc_kind=result.doc_kind,
            reason=result.reason,
            propagated_plans=result.propagated_plans,
            reused_document=result.reused_document,
        )


def is_fos_filename(filename: str) -> bool:
    return Path(filename).stem.upper().startswith("FOS_")


async def _resolve_discipline_in_plan(
    db: AsyncSession,
    *,
    study_plan_id: uuid.UUID,
    discipline_code: str,
    filename: str,
    file_bytes: bytes,
    source_ext: str,
) -> tuple[str | None, PlanDiscipline | None]:
    if source_ext == "pdf":
        code = code_from_filename(filename)
    else:
        code = resolve_discipline_code(file_bytes, filename)
    if not code:
        return None, None

    result = await db.execute(
        select(PlanDiscipline)
        .options(selectinload(PlanDiscipline.program))
        .where(
            PlanDiscipline.study_plan_id == study_plan_id,
            PlanDiscipline.code == code,
        )
    )
    discipline = result.scalar_one_or_none()

    if discipline is None:
        alt_code = code_from_filename(filename)
        if alt_code and alt_code != code:
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
                code = alt_code

    return code, discipline


async def link_document_to_program(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    study_plan_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    source_ext: str = "docx",
    propagate_all_plans: bool = False,
    rpd: RpdExtract | None = None,
    fos: FosExtract | None = None,
    file_hash: str | None = None,
    reused_document: bool = False,
) -> ProgramLinkResult:
    plan = await db.get(
        StudyPlan,
        study_plan_id,
        options=[selectinload(StudyPlan.profile)],
    )
    if plan is None:
        return ProgramLinkResult(linked=False, reason="study_plan_not_found")

    discipline_code, discipline = await _resolve_discipline_in_plan(
        db,
        study_plan_id=study_plan_id,
        discipline_code="",
        filename=filename,
        file_bytes=file_bytes,
        source_ext=source_ext,
    )
    if not discipline_code:
        return ProgramLinkResult(
            linked=False,
            study_plan_id=study_plan_id,
            reason="discipline_code_not_found",
        )
    if discipline is None:
        return ProgramLinkResult(
            linked=False,
            discipline_code=discipline_code,
            study_plan_id=study_plan_id,
            reason="discipline_not_in_plan",
        )

    doc_kind = doc_kind_from_filename(filename)

    if doc_kind == "fos" and source_ext == "pdf":
        return ProgramLinkResult(
            linked=False,
            discipline_code=discipline_code,
            study_plan_id=study_plan_id,
            reason="fos_pdf_not_supported",
        )

    if rpd is None and fos is None:
        if doc_kind == "fos":
            fos = extract_fos(file_bytes, filename)
        elif source_ext == "pdf":
            rpd = extract_rpd_from_pdf(file_bytes, filename)
        else:
            rpd = extract_rpd(file_bytes, filename)
            from app.services.text_normalizer import normalize_rpd_extract

            rpd = await normalize_rpd_extract(db, rpd)

    if propagate_all_plans or file_hash:
        result = await link_and_propagate_document(
            db,
            document_id=document_id,
            profile_id=plan.profile_id,
            discipline_code=discipline_code,
            doc_kind=doc_kind,
            primary_study_plan_id=study_plan_id,
            primary_discipline=discipline,
            propagate_all_plans=propagate_all_plans,
            rpd=rpd,
            fos=fos,
            file_hash=file_hash,
            source_filename=filename,
            reused_document=reused_document,
        )
        return ProgramLinkResult.from_propagate(result)

    await attach_document_to_discipline(
        db,
        discipline=discipline,
        document_id=document_id,
        doc_kind=doc_kind,
        rpd=rpd,
        fos=fos,
        sync_structured=not reused_document,
    )
    program = discipline.program
    return ProgramLinkResult(
        linked=True,
        discipline_code=discipline_code,
        plan_discipline_id=discipline.id,
        study_plan_id=study_plan_id,
        program_id=program.id if program else None,
        program_status=program.status if program else None,
        doc_kind=doc_kind,
        reused_document=reused_document,
    )


async def link_document_to_profile_programs(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    profile_id: uuid.UUID,
    discipline_code: str,
    doc_kind: str,
    filename: str,
    file_bytes: bytes,
    source_ext: str,
    rpd: RpdExtract | None = None,
    fos: FosExtract | None = None,
    file_hash: str | None = None,
    reused_document: bool = False,
) -> ProgramLinkResult:
    """Привязка из библиотеки направления: ко всем планам профиля с этой дисциплиной."""
    disciplines = await db.execute(
        select(PlanDiscipline)
        .join(StudyPlan, PlanDiscipline.study_plan_id == StudyPlan.id)
        .options(selectinload(PlanDiscipline.program))
        .where(
            StudyPlan.profile_id == profile_id,
            PlanDiscipline.code == discipline_code,
        )
        .order_by(StudyPlan.year.desc().nullslast())
    )
    all_disciplines = list(disciplines.scalars().all())
    if not all_disciplines:
        return ProgramLinkResult(
            linked=False,
            discipline_code=discipline_code,
            reason="discipline_not_in_plan",
        )

    primary = all_disciplines[0]
    primary_plan_id = primary.study_plan_id

    if rpd is None and fos is None:
        if doc_kind == "fos":
            fos = extract_fos(file_bytes, filename)
        elif source_ext == "pdf":
            rpd = extract_rpd_from_pdf(file_bytes, filename)
        else:
            rpd = extract_rpd(file_bytes, filename)
            from app.services.text_normalizer import normalize_rpd_extract

            rpd = await normalize_rpd_extract(db, rpd)

    result = await link_and_propagate_document(
        db,
        document_id=document_id,
        profile_id=profile_id,
        discipline_code=discipline_code,
        doc_kind=doc_kind,
        primary_study_plan_id=primary_plan_id,
        primary_discipline=primary,
        propagate_all_plans=True,
        rpd=rpd,
        fos=fos,
        file_hash=file_hash,
        source_filename=filename,
        reused_document=reused_document,
    )
    return ProgramLinkResult.from_propagate(result)
