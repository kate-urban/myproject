"""Сборка экспорта: шапка макета + всё содержимое загруженного документа."""

from __future__ import annotations

import re

from docx import Document
from docx.text.paragraph import Paragraph

from app.services.export_by_headings import _HEADING_NUMBER_RE
from app.utils.html_converter import insert_html_after_paragraph

# С этого места в макете заменяем пустой «хвост» на содержимое документа.
CONTENT_START_MARKERS: dict[str, list[str]] = {
    "fos": [
        "перечень компетенций",
        "компетенции, формируемые",
        "программа оценивания",
        "контролируем",
    ],
    "rp": [
        "1. цель и задачи",
        "1.1. цели",
        "цель и задачи дисциплины",
    ],
    "generic": [],
}


def detect_template_kind(doc: Document) -> str:
    sample = " ".join(p.text.lower() for p in doc.paragraphs[:40])
    if "фонд оценочных" in sample or "ф о н д" in sample:
        return "fos"
    if "рабочая программа" in sample or "р а б о ч а я" in sample:
        return "rp"
    return "generic"


def find_content_start_index(doc: Document, kind: str) -> int:
    markers = CONTENT_START_MARKERS.get(kind, []) + CONTENT_START_MARKERS["generic"]
    for index, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip().lower()
        if not text:
            continue
        for marker in markers:
            if marker in text:
                return index

    for index, paragraph in enumerate(doc.paragraphs):
        if _HEADING_NUMBER_RE.match(paragraph.text.strip()):
            return index

    # Оставляем типовую шапку (~15% документа), остальное — под содержимое.
    return max(0, len(doc.paragraphs) // 6)


def _truncate_body_after(anchor: Paragraph) -> None:
    from docx.oxml.ns import qn

    element = anchor._element
    while element.getnext() is not None:
        nxt = element.getnext()
        if nxt.tag == qn("w:sectPr"):
            break
        element.getparent().remove(nxt)


def assemble_document_from_sections(
    doc: Document,
    sections: list[tuple[str, str]],
    *,
    template_kind: str | None = None,
) -> int:
    """
    Удаляет пустой блок макета после шапки и вставляет все разделы документа по порядку.
    """
    if not sections:
        return 0

    kind = template_kind or detect_template_kind(doc)
    start_index = find_content_start_index(doc, kind)
    if start_index >= len(doc.paragraphs):
        anchor = doc.add_paragraph()
    else:
        anchor = doc.paragraphs[start_index]

    _truncate_body_after(anchor)
    anchor.clear()

    current = anchor
    injected = 0

    for index, (section_name, html_content) in enumerate(sections):
        if not html_content or not str(html_content).strip():
            continue

        if index == 0:
            heading_para = anchor
        else:
            heading_para = _insert_paragraph_after(current)
            current = heading_para

        run = heading_para.add_run(section_name)
        run.bold = True

        current = insert_html_after_paragraph(doc, heading_para, html_content)
        injected += 1

    return injected


def _insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    from docx.oxml import OxmlElement

    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return Paragraph(new_p, paragraph._parent)
