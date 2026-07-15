import os
import uuid
from typing import List, Optional

from app.utils.text import section_plain_text
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, Body
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, PlanDiscipline, Program, Section, StudyPlan, Template
from app.schemas import (
    BatchUploadItemOut,
    BatchUploadOut,
    DocumentOut,
    ExportRequest,
    ProgramLinkOut,
    SectionOut,
    SectionUpdate,
    TemplateOut,
)
from app.services.document_reextract import refresh_extract_for_document
from app.services.document_storage import resolve_document_source_path
from app.services.export_finalize import finalize_export_docx
from app.services.exporter import Exporter
from app.services.rpd_extractor import RpdExtract
from app.config import EDIT_LOCKS_ENABLED, EXPORT_USE_ORIGINAL
from app.api.auth_deps import get_current_user
from app.services.auth import CurrentUser
from app.utils.http_errors import public_error_message
from app.utils.upload_limits import read_upload_bytes
from app.services.edit_lock import assert_can_edit_document
from app.services.document_upload import batch_ingest_documents, ingest_document_bytes
from app.services.template_manager import list_templates, save_template, seed_layout_templates

router = APIRouter()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPORTS_DIR = os.getenv("EXPORTS_DIR", os.path.join(_PROJECT_ROOT, "exports"))
os.makedirs(EXPORTS_DIR, exist_ok=True)


async def _program_link_for_document(
    db: AsyncSession,
    doc_id: uuid.UUID,
) -> ProgramLinkOut | None:
    result = await db.execute(
        select(Program, PlanDiscipline)
        .join(PlanDiscipline, Program.plan_discipline_id == PlanDiscipline.id)
        .where(
            (Program.document_id == doc_id) | (Program.fos_document_id == doc_id)
        )
    )
    row = result.first()
    if row is None:
        return None
    program, discipline = row
    doc_kind = "fos" if program.fos_document_id == doc_id else "rpd"
    return ProgramLinkOut(
        linked=True,
        discipline_code=discipline.code,
        plan_discipline_id=discipline.id,
        study_plan_id=discipline.study_plan_id,
        program_id=program.id,
        program_status=program.status,
        doc_kind=doc_kind,
    )


@router.get("/system/info/")
async def system_info():
    from app.config import (
        DEFAULT_FOS_TEMPLATE_NAME,
        DEFAULT_RPD_TEMPLATE_NAME,
        EXPORT_FILL_REAPPROVAL,
        EXPORT_FILL_SIGNATURES,
        EXPORT_REQUIRE_REAPPROVAL,
        EXPORT_REQUIRE_VALIDATION,
    )
    from app.utils.discipline_code import PARSER_VERSION

    return {
        "code_parser_version": PARSER_VERSION,
        "validation_ui": "/validation",
        "workspace_ui": "/",
        "export": {
            "require_validation": EXPORT_REQUIRE_VALIDATION,
            "require_reapproval": EXPORT_REQUIRE_REAPPROVAL,
            "fill_signatures": EXPORT_FILL_SIGNATURES,
            "fill_reapproval": EXPORT_FILL_REAPPROVAL,
            "default_rpd_template_name": DEFAULT_RPD_TEMPLATE_NAME,
            "default_fos_template_name": DEFAULT_FOS_TEMPLATE_NAME,
        },
    }


@router.post("/upload/", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    study_plan_id: Optional[str] = Form(None),
    propagate_all_plans: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    file_bytes = await read_upload_bytes(file)
    plan_uuid: uuid.UUID | None = None
    if study_plan_id:
        try:
            plan_uuid = uuid.UUID(study_plan_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="study_plan_id должен быть UUID",
            ) from exc

    try:
        result = await ingest_document_bytes(
            db,
            file_bytes=file_bytes,
            filename=file.filename or "upload.docx",
            study_plan_id=plan_uuid,
            propagate_all_plans=propagate_all_plans,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=public_error_message(
                exc,
                fallback="Не удалось разобрать файл",
            ),
        ) from exc

    await db.commit()
    document = await get_document(str(result.document_id), db)
    document.program_link = result.program_link
    return document


@router.post("/upload/batch/", response_model=BatchUploadOut)
async def batch_upload_documents(
    study_plan_id: str = Form(...),
    files: list[UploadFile] = File(...),
    propagate_all_plans: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """Пакетная загрузка .doc/.docx: конвертация .doc и привязка к дисциплинам УП."""
    try:
        plan_uuid = uuid.UUID(study_plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="study_plan_id должен быть UUID") from exc

    plan = await db.get(StudyPlan, plan_uuid)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    if not files:
        raise HTTPException(status_code=400, detail="Не выбраны файлы")

    return await batch_ingest_documents(
        db,
        study_plan_id=plan_uuid,
        propagate_all_plans=propagate_all_plans,
        uploads=files,
    )


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
        program_link=await _program_link_for_document(db, doc.id),
    )


@router.patch("/sections/{section_id}/", response_model=SectionOut)
async def update_section(
    section_id: str,
    update_data: SectionUpdate,
    program_id: Optional[str] = Query(None, description="Контекст программы для copy-on-write"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    result = await db.execute(select(Section).where(Section.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Раздел не найден")

    prog_uuid: uuid.UUID | None = None
    if program_id:
        try:
            prog_uuid = uuid.UUID(program_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="program_id должен быть UUID") from exc

    if EDIT_LOCKS_ENABLED:
        try:
            await assert_can_edit_document(
                db,
                document_id=section.document_id,
                user=user,
                program_id=prog_uuid,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    if update_data.content is not None:
        from app.services.document_fork import (
            find_corresponding_section,
            fork_document_for_program,
            resolve_program_for_document_edit,
        )

        program = await resolve_program_for_document_edit(
            db, section.document_id, program_id=prog_uuid
        )
        if program is not None:
            new_doc_id = await fork_document_for_program(
                db,
                document_id=section.document_id,
                program_id=program.id,
            )
            if new_doc_id != section.document_id:
                mapped = await find_corresponding_section(
                    db,
                    document_id=new_doc_id,
                    section_name=section.section_name,
                    order_index=section.order_index,
                )
                if mapped is not None:
                    section = mapped

        section.content = update_data.content
        section.content_plain = section_plain_text(update_data.content)

    await db.commit()
    await db.refresh(section)
    return SectionOut.model_validate(section)


@router.post("/documents/{doc_id}/refresh-extract/")
async def refresh_document_extract(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Пересчитать rpd/fos extract из сохранённых разделов редактора (для сверки)."""
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="doc_id должен быть UUID") from exc

    try:
        doc_kind = await refresh_extract_for_document(db, doc_uuid)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await db.commit()
    return {"doc_id": doc_id, "doc_kind": doc_kind, "refreshed": True}


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
                section.content_plain = section_plain_text(section.content)
        await db.commit()

    sections_dict = {
        s.section_name: s.content
        for s in sections
        if s.content and str(s.content).strip()
    }
    sections_order = [s.section_name for s in sections]

    doc_result = await db.execute(select(Document).where(Document.id == doc_id))
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")

    template_result = await db.execute(select(Template).where(Template.id == template_id))
    template = template_result.scalar_one_or_none()
    template_name = template.name if template else None

    source_file = None
    if EXPORT_USE_ORIGINAL:
        source_file = resolve_document_source_path(document.id, source_path=document.source_path)
    try:
        output_path, stats = await Exporter.export_document(
            document_id=doc_id,
            sections_data=sections_dict,
            template_id=template_id,
            output_dir=EXPORTS_DIR,
            sections_order=sections_order,
            doc_type=document.doc_type,
            template_name=template_name,
            source_path=str(source_file) if source_file else None,
            incremental=bool(source_file),
        )
        prog_result = await db.execute(
            select(Program, PlanDiscipline)
            .join(PlanDiscipline, Program.plan_discipline_id == PlanDiscipline.id)
            .where(
                (Program.document_id == doc_id) | (Program.fos_document_id == doc_id)
            )
        )
        prog_row = prog_result.first()
        if prog_row and str(prog_row[0].document_id) == str(doc_id):
            program, discipline = prog_row
            rpd = (
                RpdExtract.from_json(program.rpd_extract_json)
                if program.rpd_extract_json
                else None
            )
            fin = finalize_export_docx(
                output_path,
                rpd=rpd,
                discipline_code=discipline.code,
                discipline_name=discipline.name,
            )
            stats.update(fin)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=public_error_message(
                e,
                fallback="Ошибка формирования DOCX",
            ),
        ) from e

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"document_{doc_id}.docx",
        headers={
            "X-Sections-Total": str(len(sections_dict)),
            "X-Sections-Injected": str(stats.get("injected", 0)),
            "X-Export-Mode": str(stats.get("mode", "")),
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

    file_bytes = await read_upload_bytes(file)
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
