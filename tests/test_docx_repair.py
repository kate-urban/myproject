"""Tests for DOCX section-property repair during export."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.services.export_by_headings import _remove_body_after, inject_sections_by_headings
from app.utils.docx_repair import ensure_document_sectpr

ROOT = Path(__file__).resolve().parents[1]
RPD_LAYOUT = ROOT / "templates" / "layout_Maket_RPd_FGOS_3.docx"


def test_remove_body_after_preserves_sectpr() -> None:
    doc = Document(RPD_LAYOUT)
    anchor = doc.paragraphs[-1]
    _remove_body_after(anchor, None)
    assert any(child.tag == qn("w:sectPr") for child in doc.element.body)
    assert len(doc.sections) == 1


def test_inject_last_heading_keeps_sections() -> None:
    doc = Document(RPD_LAYOUT)
    inject_sections_by_headings(
        doc,
        {
            "8. Материально-техническое обеспечение": (
                "<p>Тест</p><table><tr><td>A</td><td>B</td></tr></table>"
            ),
        },
    )
    assert len(doc.sections) == 1
    doc.add_table(rows=1, cols=1)


def test_ensure_document_sectpr_restores_missing() -> None:
    doc = Document()
    for child in list(doc.element.body):
        if child.tag == qn("w:sectPr"):
            doc.element.body.remove(child)
    assert len(doc.sections) == 0
    ensure_document_sectpr(doc)
    assert len(doc.sections) == 1
    doc.add_table(rows=1, cols=1)
