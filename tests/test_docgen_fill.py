"""Тесты генератора DOCX по строгим плейсхолдерам."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from scripts.docgen.fill_docx_template import DocgenError, _scan_template_placeholders, fill_template

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "docgen" / "fixtures"
EXAMPLE_DATA = FIXTURES / "example_rpd.yaml"


@pytest.fixture
def minimal_template(tmp_path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("Код: {{DISCIPLINE_CODE}}")
    doc.add_paragraph("{{DIRECTOR_LINE}}")
    doc.add_paragraph("{{SIGNATURE_DIRECTOR}}")
    path = tmp_path / "tpl.docx"
    doc.save(path)
    return path


def test_scan_template_placeholders(minimal_template: Path) -> None:
    tags = _scan_template_placeholders(minimal_template)
    assert tags == {"DISCIPLINE_CODE", "DIRECTOR_LINE", "SIGNATURE_DIRECTOR"}


def test_fill_template_strict_missing_signature(minimal_template: Path, tmp_path: Path) -> None:
    data = tmp_path / "data.yaml"
    data.write_text(
        "strict: true\n"
        "required_placeholders: [DISCIPLINE_CODE, DIRECTOR_LINE, SIGNATURE_DIRECTOR]\n"
        "placeholders:\n"
        "  DISCIPLINE_CODE: X\n"
        "  DIRECTOR_LINE: Y\n"
        "signatures:\n"
        "  SIGNATURE_DIRECTOR:\n"
        "    required: true\n"
        "    png_path: no/such/file.png\n",
        encoding="utf-8",
    )
    with pytest.raises(DocgenError, match="SIGNATURE_DIRECTOR"):
        fill_template(
            template_path=minimal_template,
            data_path=data,
            output_dir=tmp_path / "out",
        )


@pytest.mark.skipif(not EXAMPLE_DATA.is_file(), reason="example fixture missing")
def test_example_data_has_required_fields() -> None:
    import yaml

    payload = yaml.safe_load(EXAMPLE_DATA.read_text(encoding="utf-8"))
    assert "SIGNATURE_DIRECTOR" in payload["signatures"]
    assert payload["signatures"]["SIGNATURE_DIRECTOR"]["required"] is True
