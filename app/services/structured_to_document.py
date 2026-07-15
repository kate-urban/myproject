"""Запись relational topics/zuv/literature в HTML-разделы документа."""

from __future__ import annotations

import re
import uuid
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document as DocumentModel
from app.models import Program, Section
from app.services.program_content import get_program_structured


def _section_matches(name: str, *needles: str) -> bool:
    lowered = (name or "").lower()
    return any(needle in lowered for needle in needles)


def _topics_table_html(topics: list[dict]) -> str:
    rows = []
    for topic in topics:
        rows.append(
            "<tr>"
            f"<td>{escape(str(topic.get('topic_number') or ''))}</td>"
            f"<td>{escape(str(topic.get('title') or ''))}</td>"
            f"<td>{escape(str(topic.get('semester') or ''))}</td>"
            f"<td>{escape(str(topic.get('hours_lecture') or ''))}</td>"
            f"<td>{escape(str(topic.get('hours_practical') or ''))}</td>"
            f"<td>{escape(str(topic.get('hours_lab') or ''))}</td>"
            f"<td>{escape(str(topic.get('hours_sr') or ''))}</td>"
            "</tr>"
        )
    body = "".join(rows) if rows else "<tr><td colspan='7'>—</td></tr>"
    return (
        "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;width:100%'>"
        "<thead><tr>"
        "<th>№</th><th>Тема</th><th>Сем.</th>"
        "<th>Лек</th><th>Пр</th><th>Лаб</th><th>СР</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _zuv_table_html(items: list[dict]) -> str:
    type_labels = {"know": "Знать", "skill": "Уметь", "ability": "Владеть"}
    rows = []
    for item in items:
        label = type_labels.get(item.get("zuv_type") or "know", "Знать")
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('indicator_code') or ''))}</td>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(str(item.get('text') or ''))}</td>"
            f"<td>{escape(str(item.get('topic_ref') or ''))}</td>"
            "</tr>"
        )
    body = "".join(rows) if rows else "<tr><td colspan='4'>—</td></tr>"
    return (
        "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;width:100%'>"
        "<thead><tr><th>Индикатор</th><th>Тип</th><th>Формулировка</th><th>Тема</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _literature_html(items: list[dict]) -> str:
    if not items:
        return "<p>—</p>"
    parts = []
    for index, item in enumerate(items, start=1):
        citation = escape(str(item.get("citation") or ""))
        parts.append(f"<p>{index}. {citation}</p>")
    return "".join(parts)


def _replace_or_wrap_section(content: str, inner_html: str) -> str:
    if re.search(r"<table\b", content or "", re.I):
        return re.sub(
            r"<table\b[\s\S]*?</table>",
            inner_html,
            content,
            count=1,
            flags=re.I,
        )
    return inner_html


async def apply_structured_to_document(
    db: AsyncSession,
    program_id: uuid.UUID,
) -> dict[str, object]:
    program = await db.get(Program, program_id)
    if program is None:
        raise ValueError("Программа не найдена")
    if program.document_id is None:
        raise ValueError("У программы нет связанного документа РПД")

    payload = await get_program_structured(db, program_id)
    result = await db.execute(
        select(Section)
        .where(Section.document_id == program.document_id)
        .order_by(Section.order_index)
    )
    sections = list(result.scalars().all())
    if not sections:
        raise ValueError("У документа нет разделов")

    updated: list[str] = []
    for section in sections:
        name = section.section_name or ""
        if payload["topics"] and _section_matches(name, "3.1", "содержание дисциплины", "тематическ"):
            section.content = _replace_or_wrap_section(
                section.content or "",
                _topics_table_html(payload["topics"]),
            )
            updated.append(name)
        elif payload["zuv"] and _section_matches(
            name, "2.", "формируемые компетенц", "знать, уметь", "индикатор"
        ):
            section.content = _replace_or_wrap_section(
                section.content or "",
                _zuv_table_html(payload["zuv"]),
            )
            updated.append(name)
        elif payload["literature"] and _section_matches(name, "литератур", "9."):
            section.content = _literature_html(payload["literature"])
            updated.append(name)

    if not updated:
        raise ValueError(
            "Не найдены разделы для topics/zuv/литературы — проверьте названия разделов документа"
        )

    doc = await db.get(DocumentModel, program.document_id)
    return {
        "program_id": str(program_id),
        "document_id": str(program.document_id),
        "filename": doc.filename if doc else None,
        "updated_sections": updated,
    }
