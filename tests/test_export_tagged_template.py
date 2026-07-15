"""Tests for tagged {{TAG}} template export."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from app.services.export_tagged_template import (
    render_tagged_template,
    template_uses_tagged_layout,
)

ROOT = Path(__file__).resolve().parents[1]
RPD_LAYOUT = ROOT / "templates" / "layout_Maket_RPd_FGOS_3.docx"


@pytest.mark.skipif(not RPD_LAYOUT.is_file(), reason="RPD layout missing")
def test_template_uses_tagged_layout() -> None:
    assert template_uses_tagged_layout(RPD_LAYOUT) is True


@pytest.mark.skipif(not RPD_LAYOUT.is_file(), reason="RPD layout missing")
def test_render_tagged_fills_header_tags(tmp_path) -> None:
    pytest.importorskip("docxcompose")
    out = tmp_path / "out.docx"
    render_tagged_template(
        template_path=RPD_LAYOUT,
        output_path=out,
        sections_data={},
        discipline_code="B1.O.01",
        discipline_name="Тестовая дисциплина",
        direction_code="09.03.02",
        direction_name="Информационные системы",
        department_name="кафедра тест",
    )
    with zipfile.ZipFile(out) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    assert "{{DISCIPLINE_NAME}}" not in xml
    assert "{{DIRECTION_CODE}}" not in xml
    assert "Тестовая дисциплина" in xml
    assert len(re.findall(r"\{\{[A-Z0-9_]+\}\}", xml)) == 0
