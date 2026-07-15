"""Copy-on-write для общих documents (этап 3 библиотеки направления)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Program, Section
from app.services.document_storage import copy_document_source


async def count_document_program_refs(db: AsyncSession, document_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Program)
        .where(
            (Program.document_id == document_id) | (Program.fos_document_id == document_id)
        )
    )
    return int(result.scalar_one() or 0)


async def clone_document_with_sections(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> uuid.UUID:
    doc = await db.get(Document, document_id)
    if doc is None:
        raise ValueError("Документ не найден")

    new_doc_id = uuid.uuid4()
    source_path = copy_document_source(document_id, new_doc_id)
    db.add(
        Document(
            id=new_doc_id,
            filename=doc.filename,
            doc_type=doc.doc_type,
            source_path=source_path or doc.source_path,
        )
    )

    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    )
    sections = list(result.scalars().all())
    id_map: dict[uuid.UUID, uuid.UUID] = {}

    for sec in sections:
        new_sec_id = uuid.uuid4()
        id_map[sec.id] = new_sec_id
        parent_id = id_map.get(sec.parent_id) if sec.parent_id else None
        db.add(
            Section(
                id=new_sec_id,
                document_id=new_doc_id,
                parent_id=parent_id,
                section_name=sec.section_name,
                content=sec.content,
                content_plain=sec.content_plain,
                level=sec.level,
                order_index=sec.order_index,
            )
        )

    await db.flush()
    return new_doc_id


async def find_corresponding_section(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    section_name: str,
    order_index: int,
) -> Section | None:
    result = await db.execute(
        select(Section).where(
            Section.document_id == document_id,
            Section.section_name == section_name,
            Section.order_index == order_index,
        )
    )
    return result.scalar_one_or_none()


async def fork_document_for_program(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    program_id: uuid.UUID,
) -> uuid.UUID:
    """Если документ общий — клонировать и перепривязать только эту program."""
    refs = await count_document_program_refs(db, document_id)
    if refs <= 1:
        return document_id

    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")

    new_doc_id = await clone_document_with_sections(db, document_id)
    if program.document_id == document_id:
        program.document_id = new_doc_id
    elif program.fos_document_id == document_id:
        program.fos_document_id = new_doc_id
    else:
        raise ValueError("Программа не ссылается на указанный документ")

    await db.flush()
    return new_doc_id


async def resolve_program_for_document_edit(
    db: AsyncSession,
    document_id: uuid.UUID,
    *,
    program_id: uuid.UUID | None = None,
) -> Program | None:
    if program_id is not None:
        program = await db.get(Program, program_id)
        if program is None:
            return None
        if program.document_id == document_id or program.fos_document_id == document_id:
            return program
        return None

    result = await db.execute(
        select(Program).where(
            (Program.document_id == document_id) | (Program.fos_document_id == document_id)
        )
    )
    return result.scalars().first()
