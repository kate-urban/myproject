"""Сборка PDF программ для архива через макеты Layout/."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EXPORT_USE_ORIGINAL
from app.models import Document, PlanDiscipline, Program, Section
from app.services.document_storage import resolve_document_source_path
from app.services.archive_typography import apply_archive_margins, apply_typography_to_docx_bytes
from app.services.constructor_export import (
    build_constructor_docx_with_margins,
    build_constructor_pdf_bytes_async,
    docx_bytes_to_pdf_bytes_async,
    export_constructor_via_layout,
)
from app.services.export_finalize import finalize_export_docx
from app.services.export_service import resolve_template_id
from app.services.exporter import Exporter
from app.services.rpd_extractor import RpdExtract
from app.services.template_manager import seed_layout_templates


async def _load_sections(
    db: AsyncSession,
    document_id: UUID,
) -> tuple[Document, list[Section]]:
    document = await db.get(Document, document_id)
    if document is None:
        raise ValueError("Документ не найден")
    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    )
    sections = list(result.scalars().all())
    if not sections:
        raise ValueError("Разделы документа не найдены")
    return document, sections


async def export_document_docx_via_layout(
    db: AsyncSession,
    *,
    document_id: UUID,
    doc_kind: str,
    discipline: PlanDiscipline,
    program: Program,
) -> tuple[bytes, dict] | None:
    """DOCX через Exporter + Layout; None если шаблон недоступен."""
    await seed_layout_templates()
    try:
        template_id = await resolve_template_id(db, doc_kind=doc_kind)
    except ValueError:
        return None

    document, sections = await _load_sections(db, document_id)
    sections_dict = {
        s.section_name: s.content for s in sections if s.content and str(s.content).strip()
    }
    if not sections_dict:
        return None
    sections_order = [s.section_name for s in sections if s.section_name in sections_dict]

    from app.models import Template

    template = await db.get(Template, UUID(template_id))
    template_name = template.name if template else None

    source_file = None
    if EXPORT_USE_ORIGINAL:
        source_file = resolve_document_source_path(document.id, source_path=document.source_path)
    with tempfile.TemporaryDirectory() as tmp:
        output_path, stats = await Exporter.export_document(
            document_id=str(document_id),
            sections_data=sections_dict,
            template_id=template_id,
            output_dir=tmp,
            sections_order=sections_order,
            doc_type=doc_kind if doc_kind == "fos" else document.doc_type,
            template_name=template_name,
            source_path=str(source_file) if source_file else None,
            incremental=bool(source_file),
        )
        if doc_kind == "rpd":
            rpd = RpdExtract.from_json(program.rpd_extract_json) if program.rpd_extract_json else None
            stats.update(
                finalize_export_docx(
                    output_path,
                    rpd=rpd,
                    discipline_code=discipline.code,
                    discipline_name=discipline.name,
                )
            )
        raw = Path(output_path).read_bytes()
        styled = apply_typography_to_docx_bytes(raw)
        return styled, stats


async def document_pdf_via_layout(
    db: AsyncSession,
    *,
    document_id: UUID,
    doc_kind: str,
    discipline: PlanDiscipline,
    program: Program,
    fallback_title: str,
) -> bytes | None:
    exported = await export_document_docx_via_layout(
        db,
        document_id=document_id,
        doc_kind=doc_kind,
        discipline=discipline,
        program=program,
    )
    if exported is None:
        return None
    docx_bytes, _stats = exported
    pdf = await docx_bytes_to_pdf_bytes_async(docx_bytes, title=fallback_title)
    return pdf


async def constructor_pdf_via_layout(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
) -> bytes | None:
    layout = await export_constructor_via_layout(db, program, discipline, fos_only=fos_only)
    if layout is None:
        return None
    docx_bytes, _stats = layout
    docx_bytes = build_constructor_docx_with_margins(
        program,
        discipline,
        fos_only=fos_only,
        raw_bytes=docx_bytes,
    )
    pdf = await docx_bytes_to_pdf_bytes_async(docx_bytes, title=discipline.code or "program")
    return pdf


async def build_program_archive_parts_layout(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
) -> list[tuple[str, bytes]]:
    """PDF-части архива через Layout/ (Word → PDF + поля 30 мм)."""
    from app.services.constructor_export import FOS_GIA_FIELD_PREFIX, load_constructor_data, program_kind_for

    parts: list[tuple[str, bytes]] = []
    kind = program_kind_for(discipline)

    if program.document_id:
        pdf = await document_pdf_via_layout(
            db,
            document_id=program.document_id,
            doc_kind="rpd",
            discipline=discipline,
            program=program,
            fallback_title=discipline.code or "rpd",
        )
        if pdf is None:
            from app.services.constructor_export import build_document_pdf_bytes

            raw = await build_document_pdf_bytes(
                db,
                program.document_id,
                fallback_title=discipline.code or "rpd",
            )
            if raw:
                pdf = raw
        if pdf:
            parts.append(("document", pdf))
    elif program.constructor_json:
        pdf = await constructor_pdf_via_layout(db, program, discipline, fos_only=False)
        if pdf is None:
            pdf = await build_constructor_pdf_bytes_async(db, program, discipline)
        parts.append(("constructor", pdf))

    if program.fos_document_id:
        pdf = await document_pdf_via_layout(
            db,
            document_id=program.fos_document_id,
            doc_kind="fos",
            discipline=discipline,
            program=program,
            fallback_title=f"FOS_{discipline.code or 'fos'}",
        )
        if pdf is None:
            from app.services.constructor_export import build_document_pdf_bytes

            raw = await build_document_pdf_bytes(
                db,
                program.fos_document_id,
                fallback_title=f"FOS_{discipline.code or 'fos'}",
            )
            if raw:
                pdf = raw
        if pdf:
            parts.append(("fos", pdf))
    elif kind == "gia" and program.constructor_json:
        data = load_constructor_data(program)
        if any(key.startswith(FOS_GIA_FIELD_PREFIX) and data.get(key) for key in data):
            pdf = await constructor_pdf_via_layout(db, program, discipline, fos_only=True)
            if pdf is None:
                pdf = await build_constructor_pdf_bytes_async(
                    db, program, discipline, fos_only=True
                )
            parts.append(("fos_constructor", pdf))

    return parts
