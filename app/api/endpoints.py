import os
import uuid
from typing import List, Optional

from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, Body
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, Section, Template
from app.schemas import (
    DocumentOut,
    ExportRequest,
    ProgramLinkOut,
    SectionOut,
    SectionUpdate,
    TemplateOut,
)
from app.services.exporter import Exporter
from app.services.parser import DocumentParser, ParsedSection
from app.services.rpd_linker import link_document_to_program
from app.utils.link_messages import format_link_reason
from app.services.template_manager import list_templates, save_template, seed_layout_templates

router = APIRouter()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPORTS_DIR = os.getenv("EXPORTS_DIR", os.path.join(_PROJECT_ROOT, "exports"))
os.makedirs(EXPORTS_DIR, exist_ok=True)


@router.get("/system/info/")
async def system_info():
    from app.utils.discipline_code import PARSER_VERSION

    return {
        "code_parser_version": PARSER_VERSION,
        "validation_ui": "/validation",
    }


def _to_plain_text(content: str, limit: int = 1000) -> str:
    return BeautifulSoup(content, "html.parser").get_text()[:limit]


@router.post("/upload/", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    study_plan_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    ext = file.filename.split(".")[-1].lower()
    if ext not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="Поддерживаются только PDF и DOCX")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Пустой файл")

    parser = DocumentParser()
    try:
        if ext == "pdf":
            doc_type, parsed_sections = await parser.parse_pdf(file_bytes)
        else:
            doc_type, parsed_sections = await parser.parse_docx(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Не удалось разобрать файл: {e}",
        ) from e

    if not parsed_sections:
        parsed_sections = [
            ParsedSection(
                section_name="Содержание",
                content="(пустой документ)",
                level=1,
                order_index=0,
            )
        ]

    doc_id = uuid.uuid4()
    db.add(Document(id=doc_id, filename=file.filename, doc_type=doc_type))

    section_ids: list[uuid.UUID] = []
    for sec in parsed_sections:
        parent_id = (
            section_ids[sec.parent_index]
            if sec.parent_index is not None and sec.parent_index < len(section_ids)
            else None
        )
        section_id = uuid.uuid4()
        section_ids.append(section_id)
        db.add(
            Section(
                id=section_id,
                document_id=doc_id,
                parent_id=parent_id,
                section_name=sec.section_name,
                content=sec.content,
                content_plain=_to_plain_text(sec.content),
                level=sec.level,
                order_index=sec.order_index,
            )
        )

    program_link: ProgramLinkOut | None = None
    if study_plan_id and ext == "docx":
        try:
            plan_uuid = uuid.UUID(study_plan_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="study_plan_id должен быть UUID",
            ) from exc
        link_result = await link_document_to_program(
            db,
            document_id=doc_id,
            study_plan_id=plan_uuid,
            file_bytes=file_bytes,
            filename=file.filename or "upload.docx",
        )
        program_link = ProgramLinkOut(
            linked=link_result.linked,
            discipline_code=link_result.discipline_code,
            plan_discipline_id=link_result.plan_discipline_id,
            study_plan_id=link_result.study_plan_id,
            program_status=link_result.program_status,
            doc_kind=link_result.doc_kind,
            reason=link_result.reason,
            message=format_link_reason(
                link_result.reason,
                discipline_code=link_result.discipline_code,
            ),
        )

    await db.commit()
    document = await get_document(str(doc_id), db)
    document.program_link = program_link
    return document


@router.get("/documents/{doc_id}/", response_model=DocumentOut)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    result_sections = await db.execute(
        select(Section)
        .where(Section.document_id == doc_id)
        .order_by(Section.order_index)
    )
    sections = result_sections.scalars().all()

    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        doc_type=doc.doc_type,
        uploaded_at=doc.uploaded_at,
        sections=[SectionOut.model_validate(s) for s in sections],
    )


@router.patch("/sections/{section_id}/", response_model=SectionOut)
async def update_section(
    section_id: str,
    update_data: SectionUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Section).where(Section.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Раздел не найден")

    if update_data.content is not None:
        section.content = update_data.content
        section.content_plain = _to_plain_text(update_data.content)

    await db.commit()
    await db.refresh(section)
    return SectionOut.model_validate(section)


@router.get("/export/{doc_id}/")
async def export_document(
    doc_id: str,
    template_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await _export_document(doc_id, template_id, db, body=None)


@router.post("/export/{doc_id}/")
async def export_document_with_edits(
    doc_id: str,
    template_id: str = Query(...),
    body: ExportRequest = Body(default_factory=ExportRequest),
    db: AsyncSession = Depends(get_db),
):
    """Экспорт с актуальным содержимым из редактора."""
    return await _export_document(doc_id, template_id, db, body=body)


async def _export_document(
    doc_id: str,
    template_id: str,
    db: AsyncSession,
    *,
    body: ExportRequest | None,
):
    result = await db.execute(
        select(Section)
        .where(Section.document_id == doc_id)
        .order_by(Section.order_index)
    )
    sections = result.scalars().all()
    if not sections:
        raise HTTPException(status_code=404, detail="Разделы не найдены")

    if body and body.sections:
        updates = {str(item.id): item.content for item in body.sections}
        for section in sections:
            if str(section.id) in updates:
                section.content = updates[str(section.id)]
                section.content_plain = _to_plain_text(section.content)
        await db.commit()

    sections_dict = {
        s.section_name: s.content
        for s in sections
        if s.content and str(s.content).strip()
    }

    try:
        output_path, stats = await Exporter.export_document(
            document_id=doc_id,
            sections_data=sections_dict,
            template_id=template_id,
            output_dir=EXPORTS_DIR,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка формирования DOCX: {e}",
        ) from e

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"document_{doc_id}.docx",
        headers={
            "X-Sections-Total": str(len(sections_dict)),
            "X-Sections-Injected": str(stats.get("injected", 0)),
        },
    )


@router.post("/templates/", response_model=TemplateOut)
async def upload_template(
    file: UploadFile = File(...),
    name: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    ext = file.filename.split(".")[-1].lower()
    if ext != "docx":
        raise HTTPException(status_code=400, detail="Только DOCX шаблоны")

    file_bytes = await file.read()
    template_id = await save_template(file_bytes, file.filename, name or file.filename)

    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one()
    return TemplateOut.model_validate(template)


@router.get("/templates/", response_model=List[TemplateOut])
async def list_templates_endpoint(db: AsyncSession = Depends(get_db)):
    await seed_layout_templates()
    templates = await list_templates()
    return [TemplateOut.model_validate(t) for t in templates]


@router.post("/templates/seed-layout/", response_model=List[TemplateOut])
async def seed_layout_templates_endpoint(db: AsyncSession = Depends(get_db)):
    await seed_layout_templates()
    templates = await list_templates()
    return [TemplateOut.model_validate(t) for t in templates]
