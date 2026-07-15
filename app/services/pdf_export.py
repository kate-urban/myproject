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

_MM = 72.0 / 25.4  # points per mm

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
    page = doc.new_page(width=595, height=842)  # A4
    y = 72.0
    page.insert_text((72, y), title, fontsize=14, fontname="helv")
    y += 24
    for section_name, html_content in sections:
        if y > 780:
            page = doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), section_name, fontsize=11, fontname="helv")
        y += 16
        plain = html_to_plain_text(html_content or "")
        for line in plain.splitlines():
            if not line.strip():
                continue
            if y > 780:
                page = doc.new_page(width=595, height=842)
                y = 72
            page.insert_text((86, y), line[:120], fontsize=9, fontname="helv")
            y += 12
        y += 8
    doc.save(str(output_path))
    doc.close()
    return output_path


def _resolve_png_path(png_path: str | None, project_root: Path) -> Path | None:
    if not png_path:
        return None
    candidate = Path(png_path)
    if candidate.is_file():
        return candidate
    alt = project_root / "static" / "signatures" / Path(png_path).name
    if alt.is_file():
        return alt
    alt2 = project_root / png_path.lstrip("/\\")
    return alt2 if alt2.is_file() else None


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
        png = _resolve_png_path(sig.png_path, project_root)
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
    doc.save(str(pdf_path), incremental=False, garbage=4, deflate=True)
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
    pdf_path = convert_docx_to_pdf(docx_path)
    if pdf_path is None:
        pdf_path = Path(exports_dir) / f"{download_stem}.pdf"
        build_pdf_from_sections(
            title=title,
            sections=sections or [],
            output_path=pdf_path,
        )

    if EXPORT_FILL_SIGNATURES:
        signatures = await load_active_signatures(db)
        overlay_signatures(pdf_path, signatures, project_root=project_root)

    filename = f"{download_stem}.pdf"
    return str(pdf_path), filename
