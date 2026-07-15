"""Тесты переутверждения PDF (ТЗ сценарий 2)."""

from __future__ import annotations

from datetime import date

import fitz

from pathlib import Path

from dataclasses import dataclass

from app.services.export_finalize import _current_academic_year_start
from app.services.reapproval_export import (
    ReapprovalSignature,
    build_reapproval_pdf_bytes,
    build_reapproval_rows,
)


@dataclass
class _Amendment:
    enrollment_year: int
    amendment_kind: str = "none"
    protocol_ref: str | None = None
    change_summary: str | None = None
    approved_on: date | None = None


def test_reapproval_rows_empty_variant() -> None:
    rows = build_reapproval_rows(variant="empty", enrollment_year=2022)
    assert len(rows) == 3
    assert all(row == "" for row in rows)


def test_reapproval_rows_simple_variant() -> None:
    current = _current_academic_year_start()
    rows = build_reapproval_rows(variant="simple", enrollment_year=2022)
    assert "без изменений" in rows[0]
    assert f"{current - 2}/{current - 1}" in rows[0]
    assert rows[1] == ""


def test_reapproval_rows_transition_variant() -> None:
    current = _current_academic_year_start()
    rows = build_reapproval_rows(variant="transition", enrollment_year=2022)
    assert f"{current - 2}/{current - 1}" in rows[0]
    assert f"{current - 1}/{current}" in rows[1]


DEPT_NAME = "\u0418\u043d\u043e\u0441\u0442\u0440\u0430\u043d\u043d\u044b\u0445 \u044f\u0437\u044b\u043a\u043e\u0432"
SIGN_NAME = "\u0418.\u0421. \u041b\u043e\u043c\u0430\u043a\u0438\u043d\u0430"


def _pdf_text(pdf: bytes) -> str:
    return fitz.open(stream=pdf, filetype="pdf")[0].get_text().replace("\xa0", " ")


def test_reapproval_pdf_uses_template_without_debug_footer() -> None:
    pdf = build_reapproval_pdf_bytes(
        variant="simple",
        discipline_code="B1.O.13",
        discipline_name="Test discipline",
        enrollment_year=2022,
        department_name=DEPT_NAME,
        signature=ReapprovalSignature(full_name=SIGN_NAME),
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count >= 1
    text = _pdf_text(pdf)
    assert "\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u043e" not in text
    assert "\u0421\u0412\u0415\u0414\u0415\u041d\u0418\u042f \u041e \u041f\u0415\u0420\u0415\u0423\u0422\u0412\u0415\u0420\u0416\u0414\u0415\u041d\u0418\u0418" in text
    assert "\u0431\u0435\u0437 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439" in text
    assert DEPT_NAME in text
    assert SIGN_NAME in text
    assert "31" in text
    assert "\u0430\u0432\u0433\u0443\u0441\u0442\u0430" in text


def test_reapproval_pdf_transition_has_two_rows() -> None:
    pdf = build_reapproval_pdf_bytes(
        variant="transition",
        discipline_code="B1.O.13",
        discipline_name="Test discipline",
        department_name=DEPT_NAME,
        signature=ReapprovalSignature(full_name=SIGN_NAME),
    )
    text = _pdf_text(pdf)
    assert text.count("\u0431\u0435\u0437 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439") >= 1
    assert "\u0441 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f\u043c\u0438" in text
    assert text.count(DEPT_NAME) >= 2


def test_reapproval_pdf_empty_keeps_template() -> None:
    pdf = build_reapproval_pdf_bytes(
        variant="empty",
        discipline_code="B1.O.13",
        discipline_name="Test discipline",
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = doc[0].get_text()
    assert "СВЕДЕНИЯ О ПЕРЕУТВЕРЖДЕНИИ" in text
    assert "Сформировано" not in text


def test_reapproval_pdf_signature_image_above_line() -> None:
    png = Path("samples/Podpisi/Подписи/Ломакина.png")
    if not png.is_file():
        png = Path("samples/Подписи/Ломакина.png")
    if not png.is_file():
        return

    pdf = build_reapproval_pdf_bytes(
        variant="simple",
        discipline_code="B1.O.13",
        discipline_name="Test discipline",
        department_name=DEPT_NAME,
        signature=ReapprovalSignature(full_name=SIGN_NAME, png_path=str(png)),
    )
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    images = page.get_images(full=True)
    assert images, "PNG подпись должна быть вставлена в PDF"

    _, layout_cfg = __import__(
        "app.services.reapproval_export", fromlist=["_load_layout"]
    )._load_layout()
    y_off = float(layout_cfg.get("sign_line_y_offset", 16.5))
    sign_y = float(layout_cfg["rows"][0]["sign_y"])
    line_y = sign_y + y_off

    for img in page.get_image_info(xrefs=[images[0][0]]):
        bbox = fitz.Rect(img["bbox"])
        assert bbox.y1 <= line_y + 1, "нижний край подписи должен быть над чертой"
        line_x0 = float(layout_cfg.get("sign_line_x0", 230.6))
        line_x1 = float(layout_cfg.get("sign_line_x1", 328.2))
        center = (bbox.x0 + bbox.x1) / 2
        line_center = (line_x0 + line_x1) / 2
        assert abs(center - line_center) < 25, "подпись должна быть над левой чертой, не рядом с ФИО"


def test_reapproval_rows_from_amendments() -> None:
    current = _current_academic_year_start()
    amendment = _Amendment(enrollment_year=current - 1, amendment_kind="none")
    rows = build_reapproval_rows(
        variant="custom",
        amendments=[amendment],
        enrollment_year=2022,
    )
    assert f"{current - 1}/{current}" in rows[1]
