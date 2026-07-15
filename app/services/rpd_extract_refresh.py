"""Обновление rpd_extract_json при устаревшем или неполном извлечении."""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Program
from app.services.document_reextract import refresh_extract_for_document
from app.services.rpd_extractor import RpdExtract

# Ключевые поля ТЗ — если все пустые, extract считается устаревшим.
_TZ_SIGNAL_KEYS = (
    "topics31_zuv_phrases",
    "sr_rows",
    "topic_numbers",
    "matrix_36_rows",
    "section2_zuv_by_indicator",
    "sr_questions",
)


def rpd_extract_is_stale(program: Program) -> bool:
    raw = program.rpd_extract_json
    if not raw:
        return True
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return True
    if not isinstance(data, dict):
        return True
    # Старые записи без TZ-блока
    if not any(data.get(key) for key in _TZ_SIGNAL_KEYS):
        return True
    parsed = RpdExtract.from_json(raw)
    if parsed is None:
        return True
    # Есть объём, но нет ни тем, ни 3.5 — вероятно старый парсер
    if parsed.volume.contact is not None:
        has_topics = bool(parsed.topic_numbers or parsed.topics_contact_hours)
        has_sr = parsed.sr_table_total is not None or bool(parsed.sr_rows)
        if not has_topics and not has_sr:
            return True
    return False


async def ensure_fresh_rpd_extract(
    db: AsyncSession,
    program: Program,
) -> bool:
    """
    Пересобирает extract из разделов документа, если JSON устарел.
    Возвращает True, если extract был обновлён.
    """
    if program.document_id is None or not rpd_extract_is_stale(program):
        return False
    try:
        await refresh_extract_for_document(
            db,
            uuid.UUID(str(program.document_id)),
            program_id=program.id,
        )
        await db.refresh(program)
        return True
    except (ValueError, OSError):
        return False
