"""Repair common OOXML issues in Word documents opened via python-docx."""

from __future__ import annotations

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def body_has_sectpr(body) -> bool:
    return body.find(qn("w:sectPr")) is not None


def ensure_document_sectpr(doc: Document) -> bool:
    """
    Ensure the document body ends with w:sectPr.

    python-docx requires body-level section properties for add_table(), sections, etc.
    Returns True if a new sectPr was appended.
    """
    body = doc.element.body
    if body_has_sectpr(body):
        return False

    sect_pr = OxmlElement("w:sectPr")
    pg_sz = OxmlElement("w:pgSz")
    pg_sz.set(qn("w:w"), "11906")
    pg_sz.set(qn("w:h"), "16838")
    sect_pr.append(pg_sz)

    pg_mar = OxmlElement("w:pgMar")
    for side, value in (
        ("top", "1134"),
        ("right", "1134"),
        ("bottom", "1134"),
        ("left", "1134"),
        ("header", "720"),
        ("footer", "720"),
        ("gutter", "0"),
    ):
        pg_mar.set(qn(f"w:{side}"), value)
    sect_pr.append(pg_mar)

    body.append(sect_pr)
    return True
