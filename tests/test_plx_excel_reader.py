"""Unit-тесты парсера Excel *_plx.xlsx без БД."""

from io import BytesIO

import openpyxl
import pytest

from app.services.importers.plx_excel import PlxExcelReader

TITUL_TEXT = (
    'направление 08.03.01 "Строительство" '
    'профиль "Ландшафтное строительство"'
)


@pytest.fixture
def reader() -> PlxExcelReader:
    return PlxExcelReader()


def _build_sample_workbook() -> bytes:
    wb = openpyxl.Workbook()

    titul = wb.active
    titul.title = "Титул"
    titul["A1"] = TITUL_TEXT

    plan = wb.create_sheet("План")
    plan.append(["", "", "", "", "", "", "", "", "з.е.", "", "часы", ""])
    plan.append(["", "", "", "", "", "", "", "", "", "", "", ""])
    plan.append(
        [
            "Считать в плане",
            "Индекс",
            "Наименование",
            "",
            "",
            "",
            "",
            "",
            "Эксп.",
            "Факт",
            "Эксп.",
            "По плану",
            "Конт. раб.",
            "СР",
            "Контроль",
        ]
    )
    plan.append(
        ["+", "Б1.О.01", "Иностранный язык", "", "", "", "", "", 7, 7, 252, 252, 72, 153, 27]
    )
    plan.append(
        [
            "+",
            "Б2.О.03(П)",
            "Производственная практика",
            "",
            "",
            "",
            "",
            "",
            3,
            3,
            108,
            108,
            3,
            105,
            None,
        ]
    )

    comp = wb.create_sheet("Компетенции(2)")
    comp.append(["Индекс", "", "", "", "Наименование", "Формируемые компетенции"])
    comp.append(["", "", "Б1.О.01", "", "Иностранный язык", "УК-4.3; УК-4.4"])
    comp.append(
        ["", "", "Б2.О.03(П)", "", "Производственная практика", "ОПК-3.4; ПК-7.4"]
    )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_read_excel_plan_and_competencies(reader: PlxExcelReader) -> None:
    content = _build_sample_workbook()
    dto = reader.read_bytes(content, "B080301-LSTR-2026_plx.xlsx")

    assert dto.direction_code == "08.03.01"
    assert dto.profile_name == "Ландшафтное строительство"
    assert dto.year == 2026
    assert dto.form == "ochnaya"
    assert dto.source_format == "plx_excel"
    assert len(dto.disciplines) == 2

    b1 = next(d for d in dto.disciplines if d.code == "Б1.О.01")
    assert b1.credits == 7
    assert b1.hours_total == 252
    assert b1.hours_contact == 72
    assert b1.hours_sr == 153
    assert b1.hours_control == 27
    assert b1.hours_aud is None
    assert b1.competencies == ["УК-4.3", "УК-4.4"]

    practice = next(d for d in dto.disciplines if d.code == "Б2.О.03(П)")
    assert practice.credits == 3
    assert practice.hours_aud == 105
    assert practice.hours_sr is None
    assert "ОПК-3.4" in practice.competencies


def test_form_from_oz_filename(reader: PlxExcelReader) -> None:
    content = _build_sample_workbook()
    dto = reader.read_bytes(content, "B080301-LSTR-2026oz_plx.xlsx")
    assert dto.form == "ochno_zaochnaya"
