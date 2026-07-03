"""Сверка PlxExcelReader с golden_pairs.yaml на реальном B080301."""

from pathlib import Path

import pytest

from app.services.importers.plx_excel import PlxExcelReader

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
LSTR_XLSX = SAMPLES / "B080301-LSTR-2026_plx.xlsx"

GOLDEN_LSTR = {
    "Б2.О.03(П)": {
        "credits": 3,
        "hours_total": 108,
        "hours_contact": 3,
        "hours_aud": 105,
        "hours_sr": None,
        "competencies": [
            "ОПК-3.4",
            "ОПК-3.5",
            "ОПК-3.6",
            "ОПК-3.7",
            "ОПК-6.1",
            "ОПК-6.2",
            "ОПК-6.3",
            "ОПК-6.4",
            "ОПК-6.12",
            "ОПК-6.13",
            "ПК-7.4",
        ],
    },
    "Б1.В.12": {
        "credits": 2,
        "hours_total": 72,
        "hours_contact": 36,
        "hours_aud": 36,
        "hours_sr": None,
    },
    "ФТД.01": {
        "credits": 4,
        "hours_total": 144,
    },
}


@pytest.fixture
def lstr_dto():
    if not LSTR_XLSX.is_file():
        pytest.skip("samples/B080301-LSTR-2026_plx.xlsx missing")
    return PlxExcelReader().read(LSTR_XLSX)


@pytest.mark.skipif(not LSTR_XLSX.is_file(), reason="real sample missing")
def test_lstr_plan_metadata(lstr_dto) -> None:
    assert lstr_dto.direction_code == "08.03.01"
    assert lstr_dto.direction_name == "Строительство"
    assert lstr_dto.profile_name == "Ландшафтное строительство"
    assert lstr_dto.year == 2026
    assert lstr_dto.form == "ochnaya"
    assert len(lstr_dto.disciplines) >= 80


@pytest.mark.skipif(not LSTR_XLSX.is_file(), reason="real sample missing")
@pytest.mark.parametrize("code", list(GOLDEN_LSTR.keys()))
def test_lstr_golden_disciplines(lstr_dto, code: str) -> None:
    expected = GOLDEN_LSTR[code]
    discipline = next(d for d in lstr_dto.disciplines if d.code == code)

    assert discipline.credits == expected["credits"]
    assert discipline.hours_total == expected["hours_total"]

    for field in ("hours_contact", "hours_aud", "hours_sr"):
        if field in expected:
            assert getattr(discipline, field) == expected[field]

    if "competencies" in expected:
        assert set(discipline.competencies) == set(expected["competencies"])
