"""Сохранение загруженного DOCX/PDF (и конвертация .doc) в documents + привязка к УП."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from app.utils.text import section_plain_text


@dataclass
class DocumentUploadResult:
    document_id: uuid.UUID
    filename: str
    doc_type: str
    converted_from_doc: bool = False
    program_link: ProgramLinkOut | None = None
    error: str | None = None


async def ingest_document_bytes(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str,
    study_plan_id: uuid.UUID | None = None,
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
            file_bytes, filename = convert_doc_bytes_to_docx(file_bytes, filename)
        ext = "docx"
        converted_from_doc = True

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
    db.add(Document(id=doc_id, filename=filename, doc_type=doc_type))

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

    program_link: ProgramLinkOut | None = None
    if study_plan_id and ext == "docx":
        link_result = await link_document_to_program(
            db,
            document_id=doc_id,
            study_plan_id=study_plan_id,
            file_bytes=file_bytes,
            filename=filename,
        )
        program_link = ProgramLinkOut(
            linked=link_result.linked,
            discipline_code=link_result.discipline_code,
            plan_discipline_id=link_result.plan_discipline_id,
            study_plan_id=link_result.study_plan_id,
            program_id=link_result.program_id,
            program_status=link_result.program_status,
            doc_kind=link_result.doc_kind,
            reason=link_result.reason,
            message=format_link_reason(
                link_result.reason,
                discipline_code=link_result.discipline_code,
            ),
        )

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
    study_plan_id: uuid.UUID,
    uploads: list,
) -> BatchUploadOut:
    items: list[BatchUploadItemOut] = []
    linked = unlinked = errors = converted = 0

    with doc_batch_converter() as converter:
        for upload in uploads:
            name = upload.filename or "upload.docx"
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in ("doc", "docx"):
                items.append(
                    BatchUploadItemOut(
                        filename=name,
                        ok=False,
                        error="Поддерживаются только .doc и .docx",
                    )
                )
                errors += 1
                continue

            try:
                raw = await upload.read()
                result = await ingest_document_bytes(
                    db,
                    file_bytes=raw,
                    filename=name,
                    study_plan_id=study_plan_id,
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
                items.append(
                    BatchUploadItemOut(
                        filename=result.filename,
                        ok=True,
                        linked=True,
                        converted=result.converted_from_doc,
                        discipline_code=link.discipline_code,
                        doc_kind=link.doc_kind,
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
        items=items,
    )
