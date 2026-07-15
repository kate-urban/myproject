"""Типографика архива и bootstrap макетов Layout/."""

from __future__ import annotations

import fitz

from app.services.archive_typography import (
    TYPOGRAPHY,
    apply_archive_margins,
    build_text_pdf,
    insert_page_number,
)
from app.services.layout_bootstrap import ensure_layout_files


def test_typography_binding_margin() -> None:
    assert TYPOGRAPHY.binding_left_mm == 30.0
    assert TYPOGRAPHY.page_width_mm == 210.0


def test_apply_archive_margins_shifts_content() -> None:
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((10, 20), "X", fontsize=12)
    buf = doc.tobytes()
    doc.close()

    shifted = apply_archive_margins(buf, left_mm=30.0)
    out = fitz.open(stream=shifted, filetype="pdf")
    assert out[0].rect.width > 200
    out.close()


def test_build_text_pdf_renders_cyrillic() -> None:
    pdf = build_text_pdf(["Строка 1", "Строка 2"], title="Заголовок")
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = doc[0].get_text("text")
    assert "Строка" in text
    assert "Заголовок" in text
    assert "\xb7" not in text
    doc.close()


def test_insert_page_number_odd_even() -> None:
    doc = fitz.open()
    doc.new_page(width=TYPOGRAPHY.page_width_pt, height=TYPOGRAPHY.page_height_pt)
    doc.new_page(width=TYPOGRAPHY.page_width_pt, height=TYPOGRAPHY.page_height_pt)
    insert_page_number(doc[0], 1, duplex=True)
    insert_page_number(doc[1], 2, duplex=True)
    doc.close()


def test_ensure_layout_files_creates_makets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAYOUT_DIR", str(tmp_path / "Layout"))
    created = ensure_layout_files()
    assert len(created) == 6
    assert (tmp_path / "Layout" / "Maket_RPd_FGOS_3.docx").is_file()
    assert ensure_layout_files() == []
