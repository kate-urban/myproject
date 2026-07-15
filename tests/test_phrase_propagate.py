"""Тесты распространения фраз."""

from __future__ import annotations

import uuid

import pytest

from app.models import Document, Program, Section
from app.models_tz import RefPhrase
from app.services.phrase_propagate import propagate_phrase

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_propagate_phrase_replaces_in_section(db_session) -> None:
    uid = uuid.uuid4().hex[:8]
    old_text = f"Старый текст МТО {uid}"
    new_text = f"Новый текст МТО {uid}"
    phrase = RefPhrase(
        id=uuid.uuid4(),
        category="mto",
        version=1,
        text=old_text,
        is_active=True,
    )
    doc = Document(filename="t.docx", doc_type="rpd")
    db_session.add_all([phrase, doc])
    await db_session.flush()
    section = Section(
        document_id=doc.id,
        section_name="11",
        content=f"<p>{old_text} в программе</p>",
        order_index=1,
    )
    db_session.add(section)
    await db_session.commit()

    result = await propagate_phrase(
        db_session,
        phrase.id,
        mode="replace_active",
        new_text=new_text,
    )
    await db_session.refresh(section)
    assert result["sections_updated"] >= 1
    assert new_text in section.content
