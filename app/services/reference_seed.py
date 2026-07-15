"""Начальное наполнение справочников по ТЗ."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_tz import RefAbbreviation, RefPhrase


async def seed_reference_defaults(db: AsyncSession) -> None:
    defaults = [
        ("ОПР-1", "ОПР", 100, False),
        (r"ОПР-\d+", "ОПР", 90, True),
        (r"КР\.*", "Курсовая работа", 50, True),
    ]
    for pattern, replacement, priority, is_regex in defaults:
        exists = await db.execute(
            select(RefAbbreviation.id).where(
                RefAbbreviation.pattern == pattern,
                RefAbbreviation.replacement == replacement,
            )
        )
        if exists.scalar_one_or_none():
            continue
        db.add(
            RefAbbreviation(
                pattern=pattern,
                replacement=replacement,
                priority=priority,
                is_regex=is_regex,
                is_active=True,
            )
        )

    phrase_defaults = [
        ("mto", "Материально-техническое обеспечение дисциплины соответствует требованиям программы."),
        ("practice_annotation", "Практика направлена на формирование профессиональных компетенций обучающегося."),
        ("gia_annotation", "Государственная итоговая аттестация завершает освоение образовательной программы."),
    ]
    for category, text in phrase_defaults:
        exists = await db.execute(
            select(RefPhrase.id).where(
                RefPhrase.category == category,
                RefPhrase.text == text,
            )
        )
        if exists.scalar_one_or_none():
            continue
        db.add(RefPhrase(category=category, version=1, text=text, is_active=True))
    await db.flush()
