"""Финализация экспорта: паспорт, подписи PNG, переутверждение, типографика."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from docx import Document

from app.services.archive_typography import apply_typography_to_docx
from app.services.export_docx_signatures import overlay_docx_signatures
from app.services.export_passport import (
    _control_label_from_assessments,
    fill_passport_tables,
)
from app.services.rpd_extractor import RpdExtract

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _current_academic_year_start() -> int:
    override = _env("REAPPROVAL_CURRENT_YEAR")
    if override.isdigit():
        return int(override)
    today = datetime.now()
    return today.year if today.month >= 9 else today.year - 1


def _format_reapproval_rows(rpd: RpdExtract | None) -> str:
    years = sorted(set(rpd.reapproval_years if rpd else []))
    start = _current_academic_year_start()
    if start not in years:
        years.append(start)
    years = sorted(set(years))

    lines: list[str] = []
    for year in years:
        lines.append(
            f"на {year}/{year + 1} учебный год — протокол изменений от «___» __________ {year} г."
        )
    return "\n".join(lines)


def build_finalize_placeholders(
    *,
    rpd: RpdExtract | None = None,
    discipline_code: str | None = None,
    discipline_name: str | None = None,
) -> dict[str, str]:
    director = _env("EXPECTED_DIRECTOR")
    head = _env("EXPECTED_DISCIPLINE_HEAD")

    if rpd:
        director = director or (rpd.director_name or "")
        head = head or (rpd.discipline_head or "")
        discipline_code = discipline_code or rpd.discipline_code
        discipline_name = discipline_name or rpd.discipline_name

    reapproval_rows = _format_reapproval_rows(rpd)
    reapproval_years = ", ".join(str(y) for y in sorted(set(rpd.reapproval_years if rpd else [])))

    mapping = {
        "DIRECTOR_LINE": director,
        "EXPECTED_DIRECTOR": director,
        "HEAD_LINE": head,
        "DISCIPLINE_HEAD_LINE": head,
        "EXPECTED_DISCIPLINE_HEAD": head,
        "DISCIPLINE_CODE": discipline_code or "",
        "DISCIPLINE_NAME": discipline_name or "",
        "APPROVAL_YEAR": str(rpd.approval_year) if rpd and rpd.approval_year else "",
        "REAPPROVAL_YEARS": reapproval_years,
        "REAPPROVAL_ROWS": reapproval_rows,
    }
    return mapping


def _replace_in_paragraph(paragraph, mapping: dict[str, str]) -> int:
    text = paragraph.text
    if "{{" not in text:
        return 0
    hits = 0
    new_text = text
    for match in _PLACEHOLDER_RE.finditer(text):
        key = match.group(1)
        if key in mapping and mapping[key]:
            new_text = new_text.replace(match.group(0), mapping[key])
            hits += 1
    if hits and new_text != text:
        paragraph.text = new_text
    return hits


def _fill_reapproval_table(doc: Document, mapping: dict[str, str]) -> int:
    rows_text = mapping.get("REAPPROVAL_ROWS", "")
    if not rows_text:
        return 0

    filled = 0
    for table in doc.tables:
        sample = " ".join(cell.text for row in table.rows for cell in row.cells).lower()
        if "переутверж" not in sample and "протокол" not in sample:
            continue
        for row in table.rows[1:]:
            cells = row.cells
            if not cells:
                continue
            cell_text = cells[0].text.strip()
            if cell_text and cell_text not in ("", "—", "-"):
                continue
            if len(cells) >= 1:
                cells[0].text = rows_text.split("\n")[0]
                filled += 1
                break
    return filled


def finalize_export_docx(
    output_path: str,
    *,
    rpd: RpdExtract | None = None,
    discipline_code: str | None = None,
    discipline_name: str | None = None,
    direction_code: str | None = None,
    direction_name: str | None = None,
    profile_name: str | None = None,
    department_name: str | None = None,
    credits: float | None = None,
    assessments=None,
    authors: list[str] | None = None,
    signatures: list | None = None,
    fill_signatures: bool = True,
    fill_reapproval: bool = True,
    apply_typography: bool = True,
    tagged_template: bool = False,
) -> dict:
    """Паспорт + подписи PNG + переутверждение + Times New Roman."""
    from app.config import EXPORT_FILL_REAPPROVAL, EXPORT_FILL_SIGNATURES
    from app.services.archive_typography import EXPORT_TYPOGRAPHY, apply_typography_to_docx

    if tagged_template:
        doc = Document(output_path)
        if apply_typography:
            apply_typography_to_docx(doc, EXPORT_TYPOGRAPHY, justify_body=True)
        doc.save(output_path)
        return {
            "placeholders_filled": 0,
            "reapproval_rows": 0,
            "passport_filled": 0,
            "signature_cells": 0,
            "signature_paragraphs": 0,
            "tagged_template": True,
        }

    if not fill_signatures and not fill_reapproval and not apply_typography:
        return {"placeholders_filled": 0, "reapproval_rows": 0}

    mapping = build_finalize_placeholders(
        rpd=rpd,
        discipline_code=discipline_code,
        discipline_name=discipline_name,
    )

    doc = Document(output_path)
    hits = 0

    control_label = _control_label_from_assessments(assessments)
    passport_stats = fill_passport_tables(
        doc,
        rpd=rpd,
        discipline_code=discipline_code,
        discipline_name=discipline_name,
        direction_code=direction_code,
        direction_name=direction_name,
        profile_name=profile_name,
        department_name=department_name,
        credits=credits,
        control_label=control_label or None,
        authors=authors,
    )

    if fill_signatures and EXPORT_FILL_SIGNATURES:
        for paragraph in doc.paragraphs:
            hits += _replace_in_paragraph(paragraph, mapping)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        hits += _replace_in_paragraph(paragraph, mapping)

        if signatures:
            sig_stats = overlay_docx_signatures(
                doc,
                signatures=signatures,
                names={
                    "director": mapping.get("DIRECTOR_LINE", ""),
                    "discipline_head": mapping.get("HEAD_LINE", ""),
                    "dept_head": mapping.get("HEAD_LINE", ""),
                },
                project_root=_PROJECT_ROOT,
            )
        else:
            sig_stats = {"cells": 0, "paragraphs": 0}
    else:
        sig_stats = {"cells": 0, "paragraphs": 0}

    reapproval_hits = 0
    if fill_reapproval and EXPORT_FILL_REAPPROVAL:
        reapproval_hits = _fill_reapproval_table(doc, mapping)
        marker = "сведения о переутвержден"
        for index, paragraph in enumerate(doc.paragraphs):
            if marker in paragraph.text.lower() and mapping.get("REAPPROVAL_ROWS"):
                if index + 1 < len(doc.paragraphs):
                    nxt = doc.paragraphs[index + 1]
                    if not nxt.text.strip():
                        nxt.text = mapping["REAPPROVAL_ROWS"]
                        reapproval_hits += 1

    if apply_typography:
        apply_typography_to_docx(doc)

    doc.save(output_path)
    return {
        "placeholders_filled": hits,
        "reapproval_rows": reapproval_hits,
        "passport_filled": sum(passport_stats.values()),
        "signature_cells": sig_stats.get("cells", 0),
        "signature_paragraphs": sig_stats.get("paragraphs", 0),
    }
