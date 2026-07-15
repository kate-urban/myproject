"""Массовое обновление стандартных фраз в программах (ТЗ модуль 1)."""

from __future__ import annotations

import json
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Program, Section
from app.models_tz import RefPhrase


async def propagate_phrase(
    db: AsyncSession,
    phrase_id: UUID,
    *,
    mode: str = "replace_active",
    new_text: str | None = None,
) -> dict:
    """
    mode:
      - new_version: деактивировать старую, создать новую версию (+1)
      - replace_active: заменить old_text на new_text в sections и constructor_json
    """
    phrase = await db.get(RefPhrase, phrase_id)
    if phrase is None:
        raise ValueError("Фраза не найдена")
    if not phrase.is_active and mode == "replace_active":
        raise ValueError("Нельзя распространять неактивную фразу")

    old_text = phrase.text.strip()
    if mode == "new_version":
        if not new_text or not new_text.strip():
            raise ValueError("Укажите новый текст фразы")
        phrase.is_active = False
        new_row = RefPhrase(
            category=phrase.category,
            version=(phrase.version or 1) + 1,
            text=new_text.strip(),
            is_active=True,
            effective_from=phrase.effective_from,
        )
        db.add(new_row)
        await db.flush()
        replace_from = old_text
        replace_to = new_text.strip()
        target_phrase_id = new_row.id
    else:
        replace_from = old_text
        replace_to = new_text.strip() if new_text and new_text.strip() else old_text
        target_phrase_id = phrase.id

    if replace_from == replace_to:
        return {
            "phrase_id": str(target_phrase_id),
            "sections_updated": 0,
            "programs_updated": 0,
            "mode": mode,
        }

    sections_updated = 0
    programs_updated = 0

    if mode == "replace_active" or mode == "new_version":
        sections = (
            await db.execute(
                select(Section).where(
                    Section.content.isnot(None),
                    Section.content.contains(replace_from),
                )
            )
        ).scalars().all()
        for section in sections:
            if section.content and replace_from in section.content:
                section.content = section.content.replace(replace_from, replace_to)
                sections_updated += 1

        programs = (await db.execute(select(Program).where(Program.constructor_json.isnot(None)))).scalars().all()
        for program in programs:
            if not program.constructor_json:
                continue
            if replace_from not in program.constructor_json:
                continue
            try:
                data = json.loads(program.constructor_json)
            except json.JSONDecodeError:
                continue
            changed = False

            def _walk(obj):
                nonlocal changed
                if isinstance(obj, dict):
                    for key, val in obj.items():
                        if isinstance(val, str) and replace_from in val:
                            obj[key] = val.replace(replace_from, replace_to)
                            changed = True
                        else:
                            _walk(val)
                elif isinstance(obj, list):
                    for index, val in enumerate(obj):
                        if isinstance(val, str) and replace_from in val:
                            obj[index] = val.replace(replace_from, replace_to)
                            changed = True
                        else:
                            _walk(val)

            _walk(data)
            if changed:
                program.constructor_json = json.dumps(data, ensure_ascii=False)
                programs_updated += 1

    return {
        "phrase_id": str(target_phrase_id),
        "sections_updated": sections_updated,
        "programs_updated": programs_updated,
        "mode": mode,
    }
