"""CRUD реляционного тела программы: topics, zuv, literature (ТЗ P2)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Program
from app.models_tz import ProgramLiterature, ProgramTopic, ProgramZuv


def _topic_to_dict(row: ProgramTopic) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "topic_number": row.topic_number,
        "title": row.title,
        "semester": row.semester,
        "hours_lecture": row.hours_lecture,
        "hours_practical": row.hours_practical,
        "hours_lab": row.hours_lab,
        "hours_sr": row.hours_sr,
        "is_bold": row.is_bold,
        "row_order": row.row_order,
    }


def _zuv_to_dict(row: ProgramZuv) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "indicator_code": row.indicator_code,
        "zuv_type": row.zuv_type,
        "text": row.text,
        "topic_ref": row.topic_ref,
        "row_order": row.row_order,
    }


def _lit_to_dict(row: ProgramLiterature) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "citation": row.citation,
        "lit_type": row.lit_type,
        "row_order": row.row_order,
    }


async def get_program_structured(db: AsyncSession, program_id: uuid.UUID) -> dict[str, Any]:
    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")

    topics = await db.execute(
        select(ProgramTopic)
        .where(ProgramTopic.program_id == program_id)
        .order_by(ProgramTopic.row_order, ProgramTopic.topic_number)
    )
    zuv = await db.execute(
        select(ProgramZuv)
        .where(ProgramZuv.program_id == program_id)
        .order_by(ProgramZuv.row_order, ProgramZuv.indicator_code, ProgramZuv.zuv_type)
    )
    literature = await db.execute(
        select(ProgramLiterature)
        .where(ProgramLiterature.program_id == program_id)
        .order_by(ProgramLiterature.row_order)
    )

    return {
        "program_id": str(program_id),
        "program_kind": program.program_kind,
        "topics": [_topic_to_dict(row) for row in topics.scalars().all()],
        "zuv": [_zuv_to_dict(row) for row in zuv.scalars().all()],
        "literature": [_lit_to_dict(row) for row in literature.scalars().all()],
    }


async def refresh_structured_from_document(
    db: AsyncSession,
    program_id: uuid.UUID,
) -> dict[str, Any]:
    """Пересчитать extract из разделов DOC и обновить topics/zuv/literature."""
    from app.services.document_reextract import refresh_extract_for_document

    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")
    if program.document_id is None:
        raise ValueError("У программы нет связанного документа РПД")

    await refresh_extract_for_document(db, program.document_id, program_id=program.id)
    return await get_program_structured(db, program_id)


async def replace_program_topics(
    db: AsyncSession,
    program_id: uuid.UUID,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")

    await db.execute(delete(ProgramTopic).where(ProgramTopic.program_id == program_id))
    saved: list[ProgramTopic] = []
    for order, item in enumerate(items):
        title = (item.get("title") or "").strip()
        number = str(item.get("topic_number") or order + 1).strip()
        if not title:
            continue
        row = ProgramTopic(
            id=uuid.uuid4(),
            program_id=program_id,
            topic_number=number,
            title=title,
            semester=item.get("semester"),
            hours_lecture=item.get("hours_lecture"),
            hours_practical=item.get("hours_practical"),
            hours_lab=item.get("hours_lab"),
            hours_sr=item.get("hours_sr"),
            is_bold=bool(item.get("is_bold")),
            row_order=item.get("row_order", order),
        )
        db.add(row)
        saved.append(row)
    await db.flush()
    return [_topic_to_dict(row) for row in saved]


async def replace_program_zuv(
    db: AsyncSession,
    program_id: uuid.UUID,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")

    await db.execute(delete(ProgramZuv).where(ProgramZuv.program_id == program_id))
    saved: list[ProgramZuv] = []
    for order, item in enumerate(items):
        text = (item.get("text") or "").strip()
        indicator = (item.get("indicator_code") or "").strip().upper()
        if not text or not indicator:
            continue
        zuv_type = (item.get("zuv_type") or "know").strip().lower()
        if zuv_type not in {"know", "skill", "ability"}:
            zuv_type = "know"
        row = ProgramZuv(
            id=uuid.uuid4(),
            program_id=program_id,
            indicator_code=indicator,
            zuv_type=zuv_type,
            text=text,
            topic_ref=item.get("topic_ref"),
            row_order=item.get("row_order", order),
        )
        db.add(row)
        saved.append(row)
    await db.flush()
    return [_zuv_to_dict(row) for row in saved]


async def replace_program_literature(
    db: AsyncSession,
    program_id: uuid.UUID,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")

    await db.execute(delete(ProgramLiterature).where(ProgramLiterature.program_id == program_id))
    saved: list[ProgramLiterature] = []
    for order, item in enumerate(items):
        citation = (item.get("citation") or "").strip()
        if not citation:
            continue
        row = ProgramLiterature(
            id=uuid.uuid4(),
            program_id=program_id,
            citation=citation,
            lit_type=item.get("lit_type"),
            row_order=item.get("row_order", order),
        )
        db.add(row)
        saved.append(row)
    await db.flush()
    return [_lit_to_dict(row) for row in saved]
