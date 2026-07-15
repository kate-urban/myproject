"""Unit-тесты парсера XML *.plx без БД."""

from pathlib import Path

import pytest

from app.services.importers.plx_xml import PlxXmlReader

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
DESIGN_PLX = SAMPLES / "M540401-2026.plx"


@pytest.fixture
def reader() -> PlxXmlReader:
    return PlxXmlReader()


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="sample M540401-2026.plx missing")
def test_read_design_plan_metadata(reader: PlxXmlReader) -> None:
    dto = reader.read(DESIGN_PLX)

    assert dto.direction_code == "54.04.01"
    assert dto.direction_name == "Дизайн"
    assert dto.profile_name == "Экодизайн"
    assert dto.year == 2026
    assert dto.form == "ochnaya"
    assert dto.source_format == "xml_upvo"
    assert len(dto.disciplines) > 0


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="sample M540401-2026.plx missing")
@pytest.mark.parametrize(
    ("code", "hours_contact", "hours_sr"),
    [
        ("Б1.О.01.07", 150, 246),
        ("Б1.В.01.03", 54, 90),
        ("Б1.В.02.05", 54, 54),
        ("Б2.О.03(П)", 3, 645),
    ],
)
def test_read_design_hours_breakdown(
    reader: PlxXmlReader, code: str, hours_contact: int, hours_sr: int
) -> None:
    dto = reader.read(DESIGN_PLX)
    discipline = next(d for d in dto.disciplines if d.code == code)
    assert discipline.hours_contact == hours_contact
    assert discipline.hours_aud == hours_contact
    assert discipline.hours_sr == hours_sr


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="sample M540401-2026.plx missing")
def test_read_design_b1o0107_golden_pair(reader: PlxXmlReader) -> None:
    dto = reader.read(DESIGN_PLX)
    discipline = next(d for d in dto.disciplines if d.code == "Б1.О.01.07")

    assert discipline.name == "Проектная деятельность"
    assert discipline.plx_row_code == "-14"
    assert discipline.credits == 11
    assert discipline.hours_total == 396
    assert discipline.department_code == "55"
    assert len(discipline.competencies) > 0
    assert any(c.startswith("УК-") or c.startswith("ОПК-") for c in discipline.competencies)


@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="sample M540401-2026.plx missing")
def test_read_design_b1o0107_assessments(reader: PlxXmlReader) -> None:
    dto = reader.read(DESIGN_PLX)
    discipline = next(d for d in dto.disciplines if d.code == "Б1.О.01.07")
    forms = {a.form_type for a in discipline.assessments}
    assert "exam" in forms
    assert "zachet" in forms
    assert any(a.semester for a in discipline.assessments)
