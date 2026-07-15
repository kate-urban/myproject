"""Синхронизация RpdExtract → реляционные таблицы program_* (ТЗ)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import STRUCTURED_RPD_ENABLED
from app.models import Program
from app.models_tz import ProgramLiterature, ProgramTopic, ProgramZuv
from app.services.rpd_extractor import RpdExtract
from app.services.structured_rpd_sync import sync_structured_rpd
from app.utils.discipline_bucket import classify_discipline_bucket


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
        if indicator == "_ungrouped":
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
                    indicator_code=indicator.upper(),
                    zuv_type=zuv_type,
                    text=phrase.strip(),
                )
            )
            zuv_order += 1

    for order, row in enumerate(rpd.sr_rows or []):
        label = str(row.get("label") or row.get("title") or "")
        if "литератур" in label.lower():
            db.add(
                ProgramLiterature(
                    id=uuid.uuid4(),
                    program_id=program.id,
                    citation=label,
                    lit_type="main",
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
