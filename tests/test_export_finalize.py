"""Тесты финализации экспорта и правила R030."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from docx import Document

from app.services.export_finalize import build_finalize_placeholders, finalize_export_docx
from app.services.rpd_extractor import RpdExtract
from app.services.validation.rules import ValidationContext, rule_r030


def test_build_finalize_placeholders_includes_signatures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPECTED_DIRECTOR", "Директор Иванов И.И.")
    monkeypatch.setenv("EXPECTED_DISCIPLINE_HEAD", "Руководитель Петров П.П.")
    rpd = RpdExtract(discipline_code="Б1.О.01.07", approval_year=2024, reapproval_years=[2024, 2025])
    mapping = build_finalize_placeholders(rpd=rpd, discipline_code="Б1.О.01.07", discipline_name="Тест")
    assert "Иванов" in mapping["DIRECTOR_LINE"]
    assert "Петров" in mapping["HEAD_LINE"]
    assert "2024" in mapping["REAPPROVAL_YEARS"]
    assert "2024/2025" in mapping["REAPPROVAL_ROWS"]


def test_finalize_replaces_placeholders_in_docx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPECTED_DIRECTOR", "Директор Тестов")
    monkeypatch.setenv("EXPORT_FILL_SIGNATURES", "true")
    monkeypatch.setenv("EXPORT_FILL_REAPPROVAL", "false")

    path = tmp_path / "t.docx"
    doc = Document()
    doc.add_paragraph("Подпись: {{DIRECTOR_LINE}}")
    doc.save(path)

    stats = finalize_export_docx(
        str(path),
        rpd=RpdExtract(discipline_code="X"),
        discipline_code="X",
    )
    assert stats["placeholders_filled"] >= 1
    out = Document(path)
    assert "Директор Тестов" in out.paragraphs[0].text
    assert "{{DIRECTOR_LINE}}" not in out.paragraphs[0].text


def test_r030_passes_with_years() -> None:
    from types import SimpleNamespace

    rpd = RpdExtract(has_reapproval_section=True, reapproval_years=[2025])
    ctx = ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=SimpleNamespace(code="X", name="T"),
        rpd=rpd,
        plan_form="ochnaya",
    )
    result = rule_r030(ctx)
    assert result.passed is True


def test_r030_fails_when_section_empty() -> None:
    from types import SimpleNamespace

    rpd = RpdExtract(has_reapproval_section=True, reapproval_years=[])
    ctx = ValidationContext(
        direction_code="54.04.01",
        direction_name="Дизайн",
        profile_name="Экодизайн",
        discipline=SimpleNamespace(code="X", name="T"),
        rpd=rpd,
        plan_form="ochnaya",
    )
    result = rule_r030(ctx)
    assert result.passed is False
    assert result.severity == "warning"
