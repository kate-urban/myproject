"""Извлечение индикаторов компетенций из таблицы 2.1 РПД."""

from __future__ import annotations

from uuid import uuid4

from app.models import PlanDiscipline, PlanDisciplineCompetency, Program
from app.services.rpd_extractor import (
    RpdExtract,
    _bare_indicators_with_parent,
    _collect_competency_codes_from_row,
    enrich_rpd_competencies,
    extract_competency_codes_from_text,
    normalize_competency_code,
)
from app.services.validation import validate_discipline
from app.services.validation.engine import validate_program
from tests.test_validation_rules import _mock_discipline, _mock_plan


def _mock_program(*, rpd_competencies: str = "УК-4") -> Program:
    rpd = RpdExtract(discipline_code="Б1.О.01", competencies=rpd_competencies.split(";"))
    return Program(
        id=uuid4(),
        document_id=uuid4(),
        rpd_extract_json=rpd.to_json(),
        rpd_competencies=rpd_competencies,
        rpd_discipline_code="Б1.О.01",
    )


def test_normalize_competency_code_unicode_dash() -> None:
    assert normalize_competency_code("УК–4.1") == "УК-4.1"
    assert normalize_competency_code("uk-4.2") == "УК-4.2"


def test_extract_competency_codes_from_section_html() -> None:
    html = """
    <table>
      <tr><td>УК-4</td><td>Коммуникация</td>
      <td>УК–4.1 знать …; УК–4.2 уметь …; УК–4.3 владеть …;
          УК-4.4 …; УК-4.5 …</td></tr>
    </table>
    """
    codes = extract_competency_codes_from_text(html)
    assert {"УК-4.1", "УК-4.2", "УК-4.3", "УК-4.4", "УК-4.5"}.issubset(codes)


def test_r007_passes_when_codes_only_in_section_text() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline(
        competencies=[
            PlanDisciplineCompetency(competency_code="УК-4.1"),
            PlanDisciplineCompetency(competency_code="УК-4.2"),
            PlanDisciplineCompetency(competency_code="УК-4.3"),
            PlanDisciplineCompetency(competency_code="УК-4.4"),
            PlanDisciplineCompetency(competency_code="УК-4.5"),
        ]
    )
    program = _mock_program(rpd_competencies="УК-4")
    section_html = (
        "УК–4.1 знать …; УК–4.2 уметь …; УК–4.3 владеть …; "
        "УК-4.4 …; УК-4.5 …"
    )
    report = validate_program(
        plan,
        discipline,
        program,
        rule_ids=["R007"],
        section_texts=[section_html],
    )
    r007 = next(item for item in report.results if item.rule_id == "R007")
    assert r007.passed is True


class _FakeCell:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeRow:
    def __init__(self, texts: list[str]) -> None:
        self.cells = [_FakeCell(text) for text in texts]


def test_bare_indicators_with_parent_expands_subcodes() -> None:
    text = "5.1 знать основы; 5.2 уметь применять; 5.3 владеть методами"
    assert _bare_indicators_with_parent("УК-5", text) == ["УК-5.1", "УК-5.2", "УК-5.3"]


def test_collect_competency_codes_from_indicator_column() -> None:
    row = _FakeRow(
        [
            "УК-5",
            "Способность к коммуникации",
            "УК-5.1 знать …; УК-5.2 уметь …; УК-5.3 владеть …",
        ]
    )
    codes, group = _collect_competency_codes_from_row(
        row,
        code_cols={0},
        indicator_cols={2},
        current_group=None,
    )
    assert group == "УК-5"
    assert {"УК-5.1", "УК-5.2", "УК-5.3"}.issubset(codes)


def test_r007_passes_when_indicators_only_in_indicator_column() -> None:
    plan = _mock_plan()
    discipline = _mock_discipline(
        competencies=[
            PlanDisciplineCompetency(competency_code="УК-5.1"),
            PlanDisciplineCompetency(competency_code="УК-5.2"),
            PlanDisciplineCompetency(competency_code="УК-5.3"),
        ]
    )
    rpd = RpdExtract(
        discipline_code="Б1.О.01",
        competencies=["УК-5", "УК-5.1", "УК-5.2", "УК-5.3"],
        section2_zuv_by_indicator={
            "УК-5.1": ["знать …"],
            "УК-5.2": ["уметь …"],
            "УК-5.3": ["владеть …"],
        },
    )
    report = validate_discipline(plan, discipline, rpd)
    r007 = next(item for item in report.results if item.rule_id == "R007")
    assert r007.passed is True
