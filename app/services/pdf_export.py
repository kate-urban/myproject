"""Экспорт PDF с наложением PNG-подписей (ТЗ модуль 6)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID

import fitz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EXPORT_FILL_SIGNATURES
from app.models_tz import RefSignature
from app.utils.text import html_to_plain_text

from app.services.archive_typography import TYPOGRAPHY, insert_cyrillic_text
from app.services.blocking_pool import run_blocking
from app.services.signature_storage import resolve_signature_path

_MM = 72.0 / 25.4

_DEFAULT_POSITIONS: dict[str, tuple[float, float]] = {
    "director": (120.0, 255.0),
    "dept_head": (120.0, 270.0),
    "discipline_head": (120.0, 270.0),
    "reapproval": (30.0, 280.0),
}


def _find_libreoffice() -> Path | None:
    env = os.getenv("LIBREOFFICE_PATH", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("soffice")
    return Path(found) if found else None


def convert_docx_to_pdf(docx_path: str | Path) -> Path | None:
    """DOCX → PDF через LibreOffice; None если конвертер недоступен."""
    soffice = _find_libreoffice()
    if soffice is None:
        return None
    source = Path(docx_path)
    if not source.is_file():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = [
            str(soffice),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            return None
        converted = out_dir / f"{source.stem}.pdf"
        if not converted.is_file():
            return None
        target = source.with_suffix(".pdf")
        shutil.copy2(converted, target)
        return target


def build_pdf_from_sections(
    *,
    title: str,
    sections: list[tuple[str, str]],
    output_path: Path,
) -> Path:
    """Fallback: простой PDF из разделов (без LibreOffice)."""
    doc = fitz.open()
    page = doc.new_page(width=TYPOGRAPHY.page_width_pt, height=TYPOGRAPHY.page_height_pt)
    x = TYPOGRAPHY.content_left_mm * _MM
    y = TYPOGRAPHY.margin_top_mm * _MM
    max_y = TYPOGRAPHY.page_height_pt - TYPOGRAPHY.margin_bottom_mm * _MM
    line_height = TYPOGRAPHY.body_size_pt * TYPOGRAPHY.line_spacing * 0.85

    insert_cyrillic_text(page, (x, y), title, fontsize=TYPOGRAPHY.title_size_pt)
    y += line_height * 1.4
    for section_name, html_content in sections:
        if y > max_y:
            page = doc.new_page(width=TYPOGRAPHY.page_width_pt, height=TYPOGRAPHY.page_height_pt)
            y = TYPOGRAPHY.margin_top_mm * _MM
        insert_cyrillic_text(page, (x, y), section_name, fontsize=TYPOGRAPHY.body_size_pt)
        y += line_height
        plain = html_to_plain_text(html_content or "")
        for line in plain.splitlines():
            if not line.strip():
                continue
            if y > max_y:
                page = doc.new_page(width=TYPOGRAPHY.page_width_pt, height=TYPOGRAPHY.page_height_pt)
                y = TYPOGRAPHY.margin_top_mm * _MM
            insert_cyrillic_text(page, (x + 14, y), line[:120], fontsize=TYPOGRAPHY.body_size_pt - 1)
            y += line_height * 0.9
        y += line_height * 0.5
    doc.save(str(output_path))
    doc.close()
    return output_path


def overlay_signatures(
    pdf_path: Path,
    signatures: list[RefSignature],
    *,
    project_root: Path,
) -> None:
    if not signatures:
        return
    doc = fitz.open(str(pdf_path))
    for sig in signatures:
        png = resolve_signature_path(sig.png_path, project_root)
        if png is None:
            continue
        page_hint = (sig.page_hint or "title").lower()
        page_idx = 0 if page_hint in ("title", "first", "") else min(1, len(doc) - 1)
        page = doc[page_idx]
        x_mm = sig.pos_x_mm if sig.pos_x_mm is not None else _DEFAULT_POSITIONS.get(sig.role, (120, 255))[0]
        y_mm = sig.pos_y_mm if sig.pos_y_mm is not None else _DEFAULT_POSITIONS.get(sig.role, (120, 255))[1]
        rect = fitz.Rect(x_mm * _MM, y_mm * _MM, (x_mm + 45) * _MM, (y_mm + 18) * _MM)
        page.insert_image(rect, filename=str(png))
        if sig.full_name:
            page.insert_text(
                (rect.x0, rect.y1 + 4),
                sig.full_name,
                fontsize=8,
                fontname="helv",
            )
    doc.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    doc.close()


async def load_active_signatures(db: AsyncSession) -> list[RefSignature]:
    result = await db.execute(
        select(RefSignature).where(RefSignature.is_active.is_(True))
    )
    return list(result.scalars().all())


async def finalize_pdf_export(
    db: AsyncSession,
    *,
    docx_path: str,
    sections: list[tuple[str, str]] | None,
    title: str,
    download_stem: str,
    exports_dir: str,
) -> tuple[str, str]:
    """DOCX → PDF + подписи. Возвращает (path, filename)."""
    project_root = Path(__file__).resolve().parents[2]
    pdf_path = await run_blocking(convert_docx_to_pdf, docx_path)
    if pdf_path is None:
        pdf_path = Path(exports_dir) / f"{download_stem}.pdf"
        await run_blocking(
            build_pdf_from_sections,
            title=title,
            sections=sections or [],
            output_path=pdf_path,
        )

    if EXPORT_FILL_SIGNATURES:
        signatures = await load_active_signatures(db)
        await run_blocking(
            overlay_signatures,
            pdf_path,
            signatures,
            project_root=project_root,
        )

    filename = f"{download_stem}.pdf"
    return str(pdf_path), filename
