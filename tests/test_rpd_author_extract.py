"""Тесты извлечения авторов РПД (ТЗ п. 6.1, 10.1)."""

from __future__ import annotations

from app.services.rpd_extractor import (
    RpdExtract,
    authors_to_cell,
    format_author_short,
    _extract_authors,
    _names_from_text,
)
from docx import Document


def test_format_author_short_from_full_name() -> None:
    assert format_author_short("Курова Наталья Владимировна") == "Курова Н.В."


def test_format_author_short_keeps_short_form() -> None:
    assert format_author_short("Курова Н.В.") == "Курова Н.В."


def test_authors_to_cell_multiline() -> None:
    cell = authors_to_cell(["Курова Н.В.", "Киносто М.С.", "Сингуринди Э.Г."])
    assert cell == "Курова Н.В.\nКиносто М.С.\nСингуринди Э.Г."


def test_authors_to_cell_empty() -> None:
    assert authors_to_cell([]) == ""
    assert authors_to_cell(None) == ""


def test_names_from_author_label_line() -> None:
    names = _names_from_text("Курова Н.В.\nКиносто М.С.")
    assert "Курова Н.В." in names
    assert "Киносто М.С." in names


def test_extract_authors_from_passport_table() -> None:
    doc = Document()
    table = doc.add_table(rows=3, cols=2)
    table.rows[0].cells[0].text = "ФИО автора РП и ФОС"
    table.rows[0].cells[1].text = "Курова Н.В.\nКиносто М.С.\nСингуринди Э.Г."
    table.rows[1].cells[0].text = "1."
    table.rows[1].cells[1].text = "доцент"
    table.rows[2].cells[0].text = "2."
    table.rows[2].cells[1].text = "ст. преп. Петрова А.И."

    authors = _extract_authors(doc)
    assert authors == [
        "Курова Н.В.",
        "Киносто М.С.",
        "Сингуринди Э.Г.",
        "Петрова А.И.",
    ]


def test_rpd_extract_json_roundtrip_authors() -> None:
    rpd = RpdExtract(authors=["Осечкина Т.А."], passport_needs_manual=True)
    restored = RpdExtract.from_json(rpd.to_json())
    assert restored.authors == ["Осечкина Т.А."]
    assert restored.passport_needs_manual is True
