"""Пересборка DOCX из разделов редактора и обновление rpd/fos extract для сверки."""

from __future__ import annotations

import io
import uuid

from docx import Document
from docx.text.paragraph import Paragraph
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document as DocumentModel
from app.models import PlanDiscipline, Program, Section
from app.services.fos_extractor import extract_fos
from app.services.program_extract import apply_fos_extract, apply_rpd_extract
from app.services.rpd_linker import is_fos_filename
from app.services.rpd_extractor import extract_rpd
from app.utils.html_converter import insert_html_after_paragraph


def _insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    from docx.oxml import OxmlElement

    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return Paragraph(new_p, paragraph._parent)


def build_docx_bytes_from_sections(sections: list[tuple[str, str]]) -> bytes:
    doc = Document()
    anchor = doc.add_paragraph()
    anchor.clear()
    current = anchor

    for index, (section_name, html_content) in enumerate(sections):
        if index == 0:
            heading = anchor
        else:
            heading = _insert_paragraph_after(current)
            current = heading
        heading.clear()
        run = heading.add_run(section_name)
        run.bold = True
        if html_content and str(html_content).strip():
            current = insert_html_after_paragraph(doc, heading, html_content)
        else:
            current = heading

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def refresh_extract_for_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    *,
    program_id: uuid.UUID | None = None,
) -> str:
    """
    Собирает DOCX из разделов документа и обновляет rpd_extract_json / fos_extract_json
    у связанной программы. Возвращает doc_kind: 'rpd' или 'fos'.
    """
    doc = await db.get(DocumentModel, document_id)
    if doc is None:
        raise ValueError("Документ не найден")

    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    )
    db_sections = list(result.scalars().all())
    if not db_sections:
        raise ValueError("У документа нет разделов")

    pairs = [(s.section_name, s.content or "") for s in db_sections]
    file_bytes = build_docx_bytes_from_sections(pairs)
    filename = doc.filename or "document.docx"

    if program_id is not None:
        program = await db.get(Program, program_id)
    else:
        program_result = await db.execute(
            select(Program)
            .where(
                or_(
                    Program.document_id == document_id,
                    Program.fos_document_id == document_id,
                )
            )
            .limit(1)
        )
        program = program_result.scalars().first()
    if program is None:
        raise ValueError("Документ не привязан к дисциплине учебного плана")

    if program.fos_document_id == document_id or is_fos_filename(filename):
        apply_fos_extract(program, extract_fos(file_bytes, filename))
        return "fos"

    rpd = extract_rpd(file_bytes, filename)
    apply_rpd_extract(program, rpd)
    discipline = await db.get(PlanDiscipline, program.plan_discipline_id)
    from app.services.structured_program_sync import sync_program_from_extract

    await sync_program_from_extract(db, program, rpd, discipline=discipline)
    return "rpd"
