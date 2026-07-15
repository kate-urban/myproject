"""Вставка PNG-подписей и ФИО в DOCX (титул и блоки «подпись»)."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Mm
from docx.table import _Cell

from app.services.signature_storage import resolve_signature_path

_UNDERSCORE_RE = re.compile(r"_{4,}")


def _role_for_text(text: str) -> str | None:
    lowered = text.lower()
    if "директор института" in lowered or (
        "согласовано" in lowered and "директор" in lowered
    ):
        return "director"
    if "руководитель опоп" in lowered or "руководитель образовательной" in lowered:
        return "discipline_head"
    if "заведующий кафедрой" in lowered:
        return "dept_head"
    if "научный руковод" in lowered or "науч. рук" in lowered:
        return "supervisor"
    return None


def _signature_for_role(signatures: list, role: str):
    aliases = {
        "director": ("director",),
        "discipline_head": ("discipline_head", "dept_head"),
        "dept_head": ("dept_head", "discipline_head"),
        "supervisor": ("supervisor", "discipline_head", "dept_head"),
    }
    for candidate in aliases.get(role, (role,)):
        for sig in signatures:
            if getattr(sig, "role", None) == candidate and getattr(sig, "is_active", True):
                return sig
    return None


def _name_for_role(names: dict[str, str], role: str) -> str:
    for key in (role, "director", "discipline_head", "dept_head"):
        value = names.get(key, "").strip()
        if value:
            return value
    return ""


def _rebuild_signature_cell(
    cell: _Cell,
    *,
    header_lines: list[str],
    full_name: str,
    png_path: Path | None,
    width_mm: float = 38.0,
) -> None:
    cell.text = ""
    for line in header_lines:
        if line.strip():
            cell.add_paragraph(line.strip())
    if png_path is not None and png_path.is_file():
        pic_para = cell.add_paragraph()
        run = pic_para.add_run()
        run.add_picture(str(png_path), width=Mm(width_mm))
    if full_name:
        cell.add_paragraph(full_name)


def _fill_signature_cell(
    cell: _Cell,
    *,
    role: str,
    signatures: list,
    names: dict[str, str],
    project_root: Path,
) -> bool:
    sig = _signature_for_role(signatures, role)
    full_name = _name_for_role(names, role)
    if sig is not None and sig.full_name:
        full_name = sig.full_name
    png = resolve_signature_path(sig.png_path if sig else None, project_root)

    lines = [line for line in cell.text.splitlines()]
    header: list[str] = []
    for line in lines:
        if _UNDERSCORE_RE.search(line):
            break
        header.append(line)

    if not header and lines:
        header = [lines[0]]

    if not full_name and png is None:
        return False

    _rebuild_signature_cell(cell, header_lines=header, full_name=full_name, png_path=png)
    return True


def _fill_underscore_paragraph(
    paragraph,
    *,
    full_name: str,
    png_path: Path | None,
) -> bool:
    if not _UNDERSCORE_RE.search(paragraph.text):
        return False
    if not full_name and png is None:
        return False

    parent = paragraph._element.getparent()
    idx = list(parent).index(paragraph._element)

    if png_path is not None and png_path.is_file():
        from docx.oxml import OxmlElement
        from docx.text.paragraph import Paragraph

        new_p = OxmlElement("w:p")
        parent.insert(idx, new_p)
        pic_para = Paragraph(new_p, paragraph._parent)
        run = pic_para.add_run()
        run.add_picture(str(png_path), width=Mm(35))

    new_text = _UNDERSCORE_RE.sub(full_name or "________________", paragraph.text, count=1)
    paragraph.text = new_text
    return True


def overlay_docx_signatures(
    doc: Document,
    *,
    signatures: list,
    names: dict[str, str],
    project_root: Path,
) -> dict[str, int]:
    """Подписи на титуле и в блоках «(подпись)» / линиях ______."""
    stats = {"cells": 0, "paragraphs": 0}

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                role = _role_for_text(cell.text)
                if role and _fill_signature_cell(
                    cell,
                    role=role,
                    signatures=signatures,
                    names=names,
                    project_root=project_root,
                ):
                    stats["cells"] += 1

    pending_role: str | None = None
    for paragraph in doc.paragraphs:
        text = paragraph.text
        lowered = text.lower()
        role = _role_for_text(text)
        if role:
            pending_role = role

        if "(подпись)" in lowered and pending_role:
            sig = _signature_for_role(signatures, pending_role)
            full_name = _name_for_role(names, pending_role)
            if sig is not None and sig.full_name:
                full_name = sig.full_name
            png = resolve_signature_path(sig.png_path if sig else None, project_root)
            if _fill_underscore_paragraph(paragraph, full_name=full_name, png_path=png):
                stats["paragraphs"] += 1
            continue

        if _UNDERSCORE_RE.search(text) and pending_role:
            sig = _signature_for_role(signatures, pending_role)
            full_name = _name_for_role(names, pending_role)
            if sig is not None and sig.full_name:
                full_name = sig.full_name
            png = resolve_signature_path(sig.png_path if sig else None, project_root)
            if _fill_underscore_paragraph(paragraph, full_name=full_name, png_path=png):
                stats["paragraphs"] += 1

    return stats
