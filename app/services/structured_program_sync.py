"""Синхронизация RpdExtract → реляционные таблицы program_* (ТЗ)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import STRUCTURED_RPD_ENABLED
from app.models import Program, Section
from app.models_tz import ProgramLiterature, ProgramTopic, ProgramZuv
from app.services.rpd_extractor import RpdExtract
from app.services.structured_rpd_sync import sync_structured_rpd
from app.utils.discipline_bucket import classify_discipline_bucket


def _section_matches(name: str, *needles: str) -> bool:
    lowered = (name or "").lower()
    return any(needle in lowered for needle in needles)


def _literature_citations_from_html(html: str) -> list[str]:
    from bs4 import BeautifulSoup

    if not html or not str(html).strip():
        return []
    soup = BeautifulSoup(html, "html.parser")
    citations: list[str] = []
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        if len(text) > 8:
            citations.append(text)
    if citations:
        return citations
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) > 12:
            citations.append(text)
    return citations


async def _literature_from_document_sections(
    db: AsyncSession,
    program: Program,
) -> list[tuple[str, str | None]]:
    """Раздел «литература» / п.9 → строки ProgramLiterature."""
    if program.document_id is None:
        return []
    result = await db.execute(
        select(Section.section_name, Section.content)
        .where(Section.document_id == program.document_id)
        .order_by(Section.order_index)
    )
    rows: list[tuple[str, str | None]] = []
    for name, content in result.all():
        if not _section_matches(name or "", "литератур", "библиограф", "источник", "9."):
            continue
        for order, citation in enumerate(_literature_citations_from_html(content or "")):
            lit_type = "main"
            lowered = citation.lower()
            if "электрон" in lowered or "url" in lowered or "http" in lowered:
                lit_type = "electronic"
            elif "дополн" in lowered:
                lit_type = "add"
            rows.append((citation, lit_type))
    return rows


def _program_kind_for_discipline(discipline) -> str:
    bucket = classify_discipline_bucket(
        code=discipline.code,
        name=discipline.name,
        object_type=discipline.object_type,
    )
    if bucket == "gia":
        return "gia"
    if bucket == "practices":
        return "practice"
    return "discipline"


async def sync_program_from_extract(
    db: AsyncSession,
    program: Program,
    rpd: RpdExtract,
    *,
    discipline=None,
) -> None:
    """JSON-снимок + нормализованные строки topics/zuv."""
    await sync_structured_rpd(db, program, rpd)

    if discipline is not None:
        program.program_kind = _program_kind_for_discipline(discipline)

    if not STRUCTURED_RPD_ENABLED:
        return

    await db.execute(delete(ProgramTopic).where(ProgramTopic.program_id == program.id))
    await db.execute(delete(ProgramZuv).where(ProgramZuv.program_id == program.id))
    await db.execute(delete(ProgramLiterature).where(ProgramLiterature.program_id == program.id))

    for order, num in enumerate(rpd.topic_numbers):
        title = rpd.topic_names.get(num, f"Тема {num}")
        bold = any(
            item.get("number") == num for item in (rpd.topic_titles_bold or [])
        )
        db.add(
            ProgramTopic(
                id=uuid.uuid4(),
                program_id=program.id,
                topic_number=str(num),
                title=title,
                is_bold=bool(bold),
                row_order=order,
            )
        )

    zuv_order = 0
    for indicator, phrases in (rpd.section2_zuv_by_indicator or {}).items():
        if not indicator or indicator == "_ungrouped":
            continue
        indicator_code = str(indicator).strip().upper()
        if not indicator_code:
            continue
        for phrase in phrases:
            lowered = phrase.lower()
            if lowered.startswith("знать"):
                zuv_type = "know"
            elif lowered.startswith("уметь"):
                zuv_type = "skill"
            elif lowered.startswith("владеть"):
                zuv_type = "ability"
            else:
                zuv_type = "know"
            db.add(
                ProgramZuv(
                    id=uuid.uuid4(),
                    program_id=program.id,
                    indicator_code=indicator_code,
                    zuv_type=zuv_type,
                    text=phrase.strip(),
                    row_order=zuv_order,
                )
            )
            zuv_order += 1

    lit_items = await _literature_from_document_sections(db, program)
    if not lit_items:
        for row in rpd.sr_rows or []:
            label = str(row.get("label") or row.get("title") or "").strip()
            if "литератур" in label.lower() and len(label) > 15:
                lit_items.append((label, "main"))

    for order, (citation, lit_type) in enumerate(lit_items):
        db.add(
            ProgramLiterature(
                id=uuid.uuid4(),
                program_id=program.id,
                citation=citation,
                lit_type=lit_type,
                row_order=order,
            )
        )


async def load_program_topics(db: AsyncSession, program_id: uuid.UUID) -> list[ProgramTopic]:
    result = await db.execute(
        select(ProgramTopic)
        .where(ProgramTopic.program_id == program_id)
        .order_by(ProgramTopic.row_order)
    )
    return list(result.scalars().all())
