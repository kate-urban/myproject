"""Эталон типографики архивного тома и макетов (ТЗ P3, модуль 5)."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import fitz
from fitz import TextWriter
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Mm, Pt

_MM = 72.0 / 25.4


@dataclass(frozen=True)
class ArchiveTypography:
    """Параметры переплёта: A4, поле переплёта 30 мм, duplex, нумерация снаружи."""

    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    binding_left_mm: float = 30.0
    margin_right_mm: float = 15.0
    margin_top_mm: float = 20.0
    margin_bottom_mm: float = 20.0
    body_font: str = "Times New Roman"
    body_size_pt: float = 12.0
    title_size_pt: float = 14.0
    page_number_size_pt: float = 9.0
    page_number_bottom_mm: float = 12.0
    line_spacing: float = 1.5

    @property
    def content_left_mm(self) -> float:
        return self.binding_left_mm

    @property
    def page_width_pt(self) -> float:
        return self.page_width_mm * _MM

    @property
    def page_height_pt(self) -> float:
        return self.page_height_mm * _MM


TYPOGRAPHY = ArchiveTypography()
EXPORT_TYPOGRAPHY = ArchiveTypography(body_size_pt=14.0)


@lru_cache(maxsize=1)
def cyrillic_fontfile() -> str | None:
    """Times/Arial/DejaVu для кириллицы в PDF (helv её не рисует)."""
    candidates: list[Path] = []
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates.extend(windir / "Fonts" / name for name in ("times.ttf", "arial.ttf", "calibri.ttf"))
    candidates.extend(
        Path(p) / "DejaVuSerif.ttf"
        for p in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu")
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


@lru_cache(maxsize=1)
def cyrillic_font() -> fitz.Font | None:
    fontfile = cyrillic_fontfile()
    if fontfile:
        return fitz.Font(fontfile=fontfile)
    return None


def insert_cyrillic_text(
    page: fitz.Page,
    point: tuple[float, float],
    text: str,
    *,
    fontsize: float,
) -> None:
    font = cyrillic_font()
    if font is not None:
        writer = TextWriter(page.rect)
        writer.append(point, text, font=font, fontsize=fontsize)
        writer.write_text(page)
        return
    page.insert_text(point, text, fontname="helv", fontsize=fontsize)


def apply_typography_to_docx(
    doc: Document,
    spec: ArchiveTypography = TYPOGRAPHY,
    *,
    justify_body: bool = False,
) -> None:
    for section in doc.sections:
        section.page_width = Mm(spec.page_width_mm)
        section.page_height = Mm(spec.page_height_mm)
        section.left_margin = Mm(spec.binding_left_mm)
        section.right_margin = Mm(spec.margin_right_mm)
        section.top_margin = Mm(spec.margin_top_mm)
        section.bottom_margin = Mm(spec.margin_bottom_mm)

    normal = doc.styles["Normal"]
    normal.font.name = spec.body_font
    normal.font.size = Pt(spec.body_size_pt)
    pf = normal.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = spec.line_spacing
    if justify_body:
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def apply_typography_to_docx_bytes(data: bytes, spec: ArchiveTypography = TYPOGRAPHY) -> bytes:
    doc = Document(io.BytesIO(data))
    apply_typography_to_docx(doc, spec)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def apply_archive_margins(pdf_bytes: bytes, left_mm: float | None = None) -> bytes:
    """Legacy: сдвиг PDF без полей. Для архива не используется — поля задаются при генерации."""
    shift_mm = left_mm if left_mm is not None else TYPOGRAPHY.binding_left_mm
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    shift = shift_mm * _MM

    for page in src:
        rect = page.rect
        new_page = out.new_page(width=rect.width + shift, height=rect.height)
        target = fitz.Rect(shift, 0, rect.width + shift, rect.height)
        new_page.show_pdf_page(target, src, page.number)

    buffer = io.BytesIO()
    out.save(buffer, deflate=True, garbage=4)
    out.close()
    src.close()
    return buffer.getvalue()


def insert_page_number(
    page: fitz.Page,
    page_num: int,
    *,
    duplex: bool,
    spec: ArchiveTypography = TYPOGRAPHY,
) -> None:
    rect = page.rect
    y = rect.height - spec.page_number_bottom_mm * _MM
    if duplex and page_num % 2 == 0:
        x = spec.binding_left_mm * _MM
    else:
        x = max(spec.binding_left_mm * _MM, rect.width - spec.margin_right_mm * _MM - 24)
    insert_cyrillic_text(page, (x, y), str(page_num), fontsize=spec.page_number_size_pt)


def build_text_pdf(
    lines: list[str],
    *,
    title: str | None = None,
    spec: ArchiveTypography = TYPOGRAPHY,
) -> bytes:
    doc = fitz.open()
    font = cyrillic_font()
    x = spec.content_left_mm * _MM
    y = spec.margin_top_mm * _MM
    max_y = spec.page_height_pt - spec.margin_bottom_mm * _MM
    line_height = spec.body_size_pt * spec.line_spacing * 0.85
    page = doc.new_page(width=spec.page_width_pt, height=spec.page_height_pt)
    writer = TextWriter(page.rect) if font is not None else None

    def start_new_page() -> None:
        nonlocal page, writer, y
        if writer is not None:
            writer.write_text(page)
        page = doc.new_page(width=spec.page_width_pt, height=spec.page_height_pt)
        writer = TextWriter(page.rect) if font is not None else None
        y = spec.margin_top_mm * _MM

    def append_line(text: str, *, fontsize: float) -> None:
        nonlocal y
        if y > max_y:
            start_new_page()
        if writer is not None and font is not None:
            writer.append((x, y), text, font=font, fontsize=fontsize)
        else:
            insert_cyrillic_text(page, (x, y), text, fontsize=fontsize)
        y += line_height if fontsize == spec.body_size_pt else line_height * 1.4

    if title:
        append_line(title[:120], fontsize=spec.title_size_pt)
    for line in lines:
        append_line(line[:140], fontsize=spec.body_size_pt)

    if writer is not None:
        writer.write_text(page)

    buffer = io.BytesIO()
    doc.save(buffer, deflate=True, garbage=4)
    doc.close()
    return buffer.getvalue()


def build_missing_program_pdf(
    code: str,
    name: str,
    reasons: list[str],
    *,
    spec: ArchiveTypography = TYPOGRAPHY,
) -> bytes:
    lines = [
        f"{code} — {name}",
        "",
        "В архивный том не удалось включить программу:",
        *[f"• {reason}" for reason in reasons],
        "",
        "Загрузите РПД (и при необходимости ФОС) или заполните конструктор,",
        "затем нажмите «Заполнить из плана» и снова экспортируйте PDF.",
    ]
    return build_text_pdf(lines, title="Документ не собран", spec=spec)


def append_pdf_to_document(
    merged: fitz.Document,
    pdf_bytes: bytes,
    *,
    spec: ArchiveTypography = TYPOGRAPHY,
) -> int:
    """Вставляет PDF в A4-том без повторного сдвига полей."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_added = 0
    target = fitz.Rect(0, 0, spec.page_width_pt, spec.page_height_pt)
    for page in src:
        new_page = merged.new_page(width=spec.page_width_pt, height=spec.page_height_pt)
        new_page.show_pdf_page(target, src, page.number)
        pages_added += 1
    src.close()
    return pages_added


def insert_blank_page(merged: fitz.Document, spec: ArchiveTypography = TYPOGRAPHY) -> None:
    merged.new_page(width=spec.page_width_pt, height=spec.page_height_pt)


__all__ = [
    "TYPOGRAPHY",
    "EXPORT_TYPOGRAPHY",
    "ArchiveTypography",
    "apply_typography_to_docx",
    "apply_typography_to_docx_bytes",
    "apply_archive_margins",
    "append_pdf_to_document",
    "build_missing_program_pdf",
    "build_text_pdf",
    "cyrillic_font",
    "cyrillic_fontfile",
    "insert_blank_page",
    "insert_cyrillic_text",
    "insert_page_number",
]
