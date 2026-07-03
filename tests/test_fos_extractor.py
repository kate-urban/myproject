"""Тесты извлечения данных из ФОС."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.fos_extractor import extract_fos

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
FOS_FTD01 = SAMPLES / "FOS_FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx"


@pytest.mark.skipif(not FOS_FTD01.is_file(), reason="FOS FTD.01 sample missing")
def test_extract_fos_ftd01_passport() -> None:
    fos = extract_fos(FOS_FTD01.read_bytes(), FOS_FTD01.name)
    assert fos.discipline_code == "ФТД.01"
    assert fos.direction_code == "54.04.01"
    assert fos.profile_name is not None
    assert "экодизайн" in fos.profile_name.lower()
    assert fos.department_code == "52"


@pytest.mark.skipif(not FOS_FTD01.is_file(), reason="FOS FTD.01 sample missing")
def test_extract_fos_ftd01_competencies_and_control() -> None:
    fos = extract_fos(FOS_FTD01.read_bytes(), FOS_FTD01.name)
    assert "УК-5.1" in fos.indicators
    assert len(fos.control_items) >= 2
    assert all(item.indicator_code == "УК-5.1" for item in fos.control_items)
    assert len(fos.grading_criteria) >= 2
