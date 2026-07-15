"""API конструктора РПп / ГИА."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import PlanDiscipline, Program
from app.services.program_constructor import (
    get_constructor_payload,
    save_constructor_payload,
)
from app.services.constructor_export import (
    build_constructor_docx_bytes_async,
    build_constructor_docx_with_margins,
    build_constructor_pdf_bytes_async,
    export_filename,
    gia_has_fos_section,
)
from app.services.rpd_extractor import RpdExtract
from app.services.program_extract import apply_rpd_extract
from app.utils.http import attachment_disposition

router = APIRouter(prefix="/programs", tags=["programs"])


class ConstructorSaveIn(BaseModel):
    data: dict


class ProgramPassportPatch(BaseModel):
    discipline_code: str | None = None
    discipline_name: str | None = None
    direction_code: str | None = None
    profile_name: str | None = None
    department_code: str | None = None
    credits: float | None = None
    authors: list[str] | None = None
    passport_needs_manual: bool | None = None


async def _load_program(
    db: AsyncSession, program_id: UUID
) -> tuple[Program, PlanDiscipline]:
    result = await db.execute(
        select(Program)
        .options(selectinload(Program.discipline))
        .where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None or program.discipline is None:
        raise HTTPException(status_code=404, detail="Программа не найдена")
    return program, program.discipline


@router.get("/{program_id}/constructor/")
async def read_constructor(program_id: UUID, db: AsyncSession = Depends(get_db)):
    program, discipline = await _load_program(db, program_id)
    return await get_constructor_payload(db, program, discipline)


@router.put("/{program_id}/constructor/")
async def write_constructor(
    program_id: UUID,
    body: ConstructorSaveIn,
    db: AsyncSession = Depends(get_db),
):
    program, discipline = await _load_program(db, program_id)
    try:
        payload = await save_constructor_payload(
            db, program, discipline, body.data
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.get("/{program_id}/constructor/export.docx")
async def export_constructor_docx(program_id: UUID, db: AsyncSession = Depends(get_db)):
    program, discipline = await _load_program(db, program_id)
    payload = await get_constructor_payload(db, program, discipline)
    if not payload.get("supported"):
        raise HTTPException(status_code=422, detail=payload.get("message", "Конструктор недоступен"))
    raw = await build_constructor_docx_bytes_async(db, program, discipline)
    content = build_constructor_docx_with_margins(program, discipline, raw_bytes=raw)
    filename = export_filename(discipline)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=attachment_disposition(filename),
    )


@router.get("/{program_id}/constructor/export-fos.docx")
async def export_constructor_fos_docx(program_id: UUID, db: AsyncSession = Depends(get_db)):
    program, discipline = await _load_program(db, program_id)
    if (program.program_kind or "") != "gia":
        raise HTTPException(status_code=422, detail="ФОС конструктора доступен только для ГИА")
    if not gia_has_fos_section(program) and not program.fos_document_id:
        raise HTTPException(status_code=422, detail="Заполните раздел ФОС в конструкторе ГИА")
    raw = await build_constructor_docx_bytes_async(db, program, discipline, fos_only=True)
    content = build_constructor_docx_with_margins(program, discipline, fos_only=True, raw_bytes=raw)
    filename = export_filename(discipline, fos=True)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=attachment_disposition(filename),
    )


@router.get("/{program_id}/constructor/export.pdf")
async def export_constructor_pdf(program_id: UUID, db: AsyncSession = Depends(get_db)):
    program, discipline = await _load_program(db, program_id)
    payload = await get_constructor_payload(db, program, discipline)
    if not payload.get("supported"):
        raise HTTPException(status_code=422, detail=payload.get("message", "Конструктор недоступен"))
    pdf_bytes = await build_constructor_pdf_bytes_async(db, program, discipline)
    code = (discipline.code or "program").replace("/", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=attachment_disposition(f"{code}.pdf"),
    )


@router.patch("/{program_id}/passport/")
async def patch_program_passport(
    program_id: UUID,
    body: ProgramPassportPatch,
    db: AsyncSession = Depends(get_db),
):
    """Ручной ввод/правка паспорта РПД (PDF legacy, OCR fallback)."""
    program, _discipline = await _load_program(db, program_id)
    rpd = RpdExtract.from_json(program.rpd_extract_json) if program.rpd_extract_json else RpdExtract()

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if hasattr(rpd, key):
            setattr(rpd, key, value)

    if body.authors is not None:
        from app.services.rpd_extractor import format_author_short

        rpd.authors = [format_author_short(name) for name in body.authors if name.strip()]

    if body.passport_needs_manual is False or body.discipline_code or body.authors:
        rpd.passport_needs_manual = body.passport_needs_manual if body.passport_needs_manual is not None else False

    apply_rpd_extract(program, rpd)
    await db.commit()
    return {
        "program_id": str(program.id),
        "passport": {
            "discipline_code": rpd.discipline_code,
            "discipline_name": rpd.discipline_name,
            "authors": rpd.authors,
            "passport_needs_manual": rpd.passport_needs_manual,
            "passport_text_quality": rpd.passport_text_quality,
        },
    }
