"""Сохранение загруженного DOCX/PDF (и конвертация .doc) в documents + привязка к УП."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Section
from app.schemas import BatchUploadItemOut, BatchUploadOut, ProgramLinkOut
from app.services.direction_library import (
    content_hash,
    doc_kind_from_filename,
    find_library_document_by_hash,
)
from app.services.document_storage import save_document_source
from app.services.blocking_pool import run_blocking
from app.services.doc_converter import DocBatchConverter, convert_doc_bytes_to_docx, doc_batch_converter
from app.services.parser import DocumentParser, ParsedSection
from app.services.rpd_linker import (
    ProgramLinkResult,
    link_document_to_profile_programs,
    link_document_to_program,
)
from app.utils.upload_limits import read_upload_bytes
from app.utils.discipline_code import code_from_filename, resolve_discipline_code
from app.utils.link_messages import format_link_reason
from app.utils.text import section_plain_text


@dataclass
class DocumentUploadResult:
    document_id: uuid.UUID
    filename: str
    doc_type: str
    converted_from_doc: bool = False
    program_link: ProgramLinkOut | None = None
    error: str | None = None


def _link_to_schema(link: ProgramLinkResult | None) -> ProgramLinkOut | None:
    if link is None:
        return None
    return ProgramLinkOut(
        linked=link.linked,
        discipline_code=link.discipline_code,
        plan_discipline_id=link.plan_discipline_id,
        study_plan_id=link.study_plan_id,
        program_id=link.program_id,
        program_status=link.program_status,
        doc_kind=link.doc_kind,
        reason=link.reason,
        message=format_link_reason(link.reason, discipline_code=link.discipline_code),
        propagated_plans=link.propagated_plans,
        reused_document=link.reused_document,
    )


async def _store_parsed_document(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str,
    ext: str,
) -> tuple[uuid.UUID, str]:
    parser = DocumentParser()
    if ext == "pdf":
        doc_type, parsed_sections = await parser.parse_pdf(file_bytes)
    else:
        doc_type, parsed_sections = await parser.parse_docx(file_bytes)

    if not parsed_sections:
        parsed_sections = [
            ParsedSection(
                section_name="Содержание",
                content="(пустой документ)",
                level=1,
                order_index=0,
            )
        ]

    if ext == "docx" and filename.upper().startswith("FOS_"):
        doc_type = "fos"

    doc_id = uuid.uuid4()
    source_path = None
    if ext == "docx":
        source_path = save_document_source(doc_id, file_bytes)

    db.add(
        Document(
            id=doc_id,
            filename=filename,
            doc_type=doc_type,
            source_path=source_path,
        )
    )

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
                content_plain=section_plain_text(sec.content),
                level=sec.level,
                order_index=sec.order_index,
            )
        )
    return doc_id, doc_type


async def ingest_document_bytes(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str,
    study_plan_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    propagate_all_plans: bool = False,
    converter: DocBatchConverter | None = None,
) -> DocumentUploadResult:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ("pdf", "docx", "doc"):
        raise ValueError("Поддерживаются PDF, DOCX и DOC")

    if not file_bytes:
        raise ValueError("Пустой файл")

    converted_from_doc = False
    if ext == "doc":
        if converter is not None:
            file_bytes, filename = converter.to_docx_bytes(file_bytes, filename)
        else:
            file_bytes, filename = await run_blocking(
                convert_doc_bytes_to_docx, file_bytes, filename
            )
        ext = "docx"
        converted_from_doc = True

    file_hash = content_hash(file_bytes)
    doc_kind = doc_kind_from_filename(filename)
    reused_document = False
    doc_id: uuid.UUID
    doc_type: str

    if profile_id is not None:
        existing_id = await find_library_document_by_hash(
            db,
            profile_id=profile_id,
            file_hash=file_hash,
            doc_kind=doc_kind,
        )
        if existing_id is not None:
            doc_id = existing_id
            reused_document = True
            doc_type = "fos" if doc_kind == "fos" else "rp"
        else:
            doc_id, doc_type = await _store_parsed_document(
                db, file_bytes=file_bytes, filename=filename, ext=ext
            )
    elif study_plan_id is not None:
        from app.models import StudyPlan

        plan = await db.get(StudyPlan, study_plan_id)
        if plan is not None:
            existing_id = await find_library_document_by_hash(
                db,
                profile_id=plan.profile_id,
                file_hash=file_hash,
                doc_kind=doc_kind,
            )
            if existing_id is not None:
                doc_id = existing_id
                reused_document = True
                doc_type = "fos" if doc_kind == "fos" else "rp"
            else:
                doc_id, doc_type = await _store_parsed_document(
                    db, file_bytes=file_bytes, filename=filename, ext=ext
                )
        else:
            doc_id, doc_type = await _store_parsed_document(
                db, file_bytes=file_bytes, filename=filename, ext=ext
            )
    else:
        doc_id, doc_type = await _store_parsed_document(
            db, file_bytes=file_bytes, filename=filename, ext=ext
        )

    program_link: ProgramLinkOut | None = None

    if profile_id and ext in ("docx", "pdf"):
        discipline_code = (
            code_from_filename(filename)
            if ext == "pdf"
            else resolve_discipline_code(file_bytes, filename)
        )
        if discipline_code:
            link_result = await link_document_to_profile_programs(
                db,
                document_id=doc_id,
                profile_id=profile_id,
                discipline_code=discipline_code,
                doc_kind=doc_kind,
                filename=filename,
                file_bytes=file_bytes,
                source_ext=ext,
                file_hash=file_hash,
                reused_document=reused_document,
            )
            program_link = _link_to_schema(link_result)
    elif study_plan_id and ext in ("docx", "pdf"):
        link_result = await link_document_to_program(
            db,
            document_id=doc_id,
            study_plan_id=study_plan_id,
            file_bytes=file_bytes,
            filename=filename,
            source_ext=ext,
            propagate_all_plans=propagate_all_plans,
            file_hash=file_hash,
            reused_document=reused_document,
        )
        program_link = _link_to_schema(link_result)

    return DocumentUploadResult(
        document_id=doc_id,
        filename=filename,
        doc_type=doc_type,
        converted_from_doc=converted_from_doc,
        program_link=program_link,
    )


async def batch_ingest_documents(
    db: AsyncSession,
    *,
    study_plan_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    propagate_all_plans: bool = False,
    uploads: list,
) -> BatchUploadOut:
    items: list[BatchUploadItemOut] = []
    linked = unlinked = errors = converted = 0
    propagated_total = 0

    with doc_batch_converter() as converter:
        for upload in uploads:
            name = upload.filename or "upload.docx"
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in ("doc", "docx", "pdf"):
                items.append(
                    BatchUploadItemOut(
                        filename=name,
                        ok=False,
                        error="Поддерживаются .doc, .docx и .pdf",
                    )
                )
                errors += 1
                continue

            if name.startswith("~$"):
                items.append(
                    BatchUploadItemOut(
                        filename=name,
                        ok=False,
                        error="Временный файл Word (~$) — пропущен",
                    )
                )
                errors += 1
                continue

            try:
                raw = await read_upload_bytes(upload)
                result = await ingest_document_bytes(
                    db,
                    file_bytes=raw,
                    filename=name,
                    study_plan_id=study_plan_id,
                    profile_id=profile_id,
                    propagate_all_plans=propagate_all_plans,
                    converter=converter if ext == "doc" else None,
                )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                items.append(
                    BatchUploadItemOut(filename=name, ok=False, error=str(exc))
                )
                errors += 1
                continue

            if result.converted_from_doc:
                converted += 1

            link = result.program_link
            if link and link.linked:
                linked += 1
                propagated_total += link.propagated_plans or 0
                note = ""
                if link.reused_document:
                    note = " · файл из библиотеки"
                if link.propagated_plans:
                    note += f" · +{link.propagated_plans} планов"
                items.append(
                    BatchUploadItemOut(
                        filename=result.filename,
                        ok=True,
                        linked=True,
                        converted=result.converted_from_doc,
                        discipline_code=link.discipline_code,
                        doc_kind=link.doc_kind,
                        propagated_plans=link.propagated_plans,
                        reused_document=link.reused_document,
                        error=note.strip(" ·") or None,
                    )
                )
            else:
                unlinked += 1
                reason = link.message if link else "не привязан к дисциплине"
                items.append(
                    BatchUploadItemOut(
                        filename=result.filename,
                        ok=True,
                        linked=False,
                        converted=result.converted_from_doc,
                        error=reason,
                    )
                )

    return BatchUploadOut(
        total=len(items),
        linked=linked,
        unlinked=unlinked,
        errors=errors,
        converted=converted,
        propagated_plans=propagated_total,
        items=items,
    )
