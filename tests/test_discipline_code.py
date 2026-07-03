"""Тесты парсера шифров дисциплин."""

from __future__ import annotations

from unittest.mock import patch

from app.utils.discipline_code import (
    _is_incomplete_code,
    _pick_best_code,
    code_from_filename,
    resolve_discipline_code,
)


def test_incomplete_code_detection() -> None:
    assert _is_incomplete_code("Б1.В") is True
    assert _is_incomplete_code("Б1.О") is True
    assert _is_incomplete_code("Б1.В.01.03") is False
    assert _is_incomplete_code("Б1.В.ДВ.01.01") is False
    assert _is_incomplete_code("ФТД.01") is False


def test_pick_best_code_prefers_longer() -> None:
    assert _pick_best_code("Б1.В", "Б1.В.ДВ.01.01") == "Б1.В.ДВ.01.01"
    assert _pick_best_code("Б1.В.01.03", "Б1.В") == "Б1.В.01.03"


def test_filename_dv_pattern() -> None:
    assert (
        code_from_filename("B1_V_DV_01_01_Innovatsionny_menedzhment_k51.docx")
        == "Б1.В.ДВ.01.01"
    )
    assert (
        code_from_filename("FOS_B1_V_DV_01_01_Innovatsionny_menedzhment_k51.docx")
        == "Б1.В.ДВ.01.01"
    )


def test_resolve_prefers_filename_over_incomplete_passport() -> None:
    with patch(
        "app.utils.discipline_code.extract_passport_from_docx",
        return_value={"discipline_code": "Б1.В"},
    ):
        code = resolve_discipline_code(
            b"x",
            "B1_V_DV_01_01_Innovatsionny_menedzhment_k51.docx",
        )
    assert code == "Б1.В.ДВ.01.01"
