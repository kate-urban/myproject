"""Импорт кафедр из Excel."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.department_import import parse_departments_from_xlsx

ROOT = Path(__file__).resolve().parents[1]
SVOD = ROOT / "samples" / "Информационные материалы" / "2023_god_priema_SVOD_po_UP_FGOS3.xlsx"
PLAN_SUMMARY = ROOT / "samples" / "Информационные материалы" / "plan_summary_e5aaf33b-f301-4d00-90f7-82c6ebe8c8ef.xlsx"
REPORT_72 = ROOT / "samples" / "Информационные материалы" / "Otchet_po_razrabotke_RPd_2025_1.xlsx"


def test_parse_svod_departments() -> None:
    if not SVOD.is_file():
        pytest.skip("sample SVOD xlsx missing")
    rows, warnings = parse_departments_from_xlsx(SVOD)
    assert len(rows) >= 20
    codes = {r.code for r in rows}
    assert "52" in codes or "4" in codes
    assert all(r.name for r in rows)


def test_plan_summary_has_only_codes_warning() -> None:
    if not PLAN_SUMMARY.is_file():
        pytest.skip("sample plan_summary xlsx missing")
    rows, warnings = parse_departments_from_xlsx(PLAN_SUMMARY)
    assert rows == []
    assert any("нет названия" in w.lower() or "не найдено" in w.lower() for w in warnings)


def test_parse_report_72_spravochnik() -> None:
    if not REPORT_72.is_file():
        pytest.skip("sample report 7.2 xlsx missing")
    rows, _ = parse_departments_from_xlsx(REPORT_72)
    assert len(rows) >= 10
    sample = next(r for r in rows if r.code == "55")
    assert "моделирован" in sample.name.lower()
