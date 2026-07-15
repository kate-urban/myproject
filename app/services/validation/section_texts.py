"""Загрузка полного текста разделов документа для дополнения извлечения РПД."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Section
from app.utils.text import html_to_plain_text


async def load_section_texts_by_document(
    db: AsyncSession,
    document_ids: list[UUID],
) -> dict[str, list[str]]:
    if not document_ids:
        return {}

    unique_ids = list(dict.fromkeys(document_ids))
    result = await db.execute(
        select(Section.document_id, Section.content, Section.content_plain).where(
            Section.document_id.in_(unique_ids)
        )
    )

    by_document: dict[str, list[str]] = {}
    for document_id, content, content_plain in result.all():
        if content:
            text = html_to_plain_text(content)
        elif content_plain:
            text = content_plain
        else:
            continue
        by_document.setdefault(str(document_id), []).append(text)
    return by_document


def document_ids_from_disciplines(disciplines) -> list[UUID]:
    ids: list[UUID] = []
    seen: set[UUID] = set()
    for discipline in disciplines:
        program = discipline.program
        if program is None or program.document_id is None:
            continue
        if program.document_id in seen:
            continue
        seen.add(program.document_id)
        ids.append(program.document_id)
    return ids
