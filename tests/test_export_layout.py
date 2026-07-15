"""Тесты экспорта в макеты из Layout/."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from docx import Document

from app.services.exporter import Exporter
from app.services.export_by_headings import headings_match, inject_sections_by_headings
from app.services.parser import DocumentParser
from app.services.template_manager import LAYOUT_TEMPLATES, seed_layout_templates

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RPD = ROOT / "samples" / "B1_O_01_07_Proektnaya_deyatelnost_k55.docx"
MAKET_RPD = ROOT / "Layout" / "Maket_RPd_FGOS_3.docx"


@pytest.mark.parametrize(
    ("section", "heading", "expected"),
    [
        ("1.1. Цели и задачи дисциплины", "1.1. Цели и задачи дисциплины", True),
        (
            "1.2. Место дисциплины в структуре образовательной программы",
            "1.2. Место дисциплины",
            True,
        ),
        (
            "2.1 Универсальные компетенции и индикаторы их достижения",
            "2.1\tУниверсальные компетенции и индикаторы их достижения",
            True,
        ),
        ("9. Несуществующий раздел", "1.1. Цели и задачи дисциплины", False),
    ],
)
def test_headings_match(section: str, heading: str, expected: bool) -> None:
    assert headings_match(section, heading) is expected


@pytest.mark.skipif(not MAKET_RPD.is_file(), reason="Layout maket missing")
@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample RPD missing")
@pytest.mark.asyncio
async def test_inject_rpd_sections_into_maket() -> None:
    data = SAMPLE_RPD.read_bytes()
    _, sections = await DocumentParser().parse_docx(data)
    sections_data = {
        s.section_name: s.content
        for s in sections
        if s.content and s.content.strip()
    }
    assert sections_data

    doc = Document(MAKET_RPD)
    injected = inject_sections_by_headings(doc, sections_data)
    assert injected >= 5

    exported_text = "\n".join(p.text for p in doc.paragraphs)
    assert "цель" in exported_text.lower() or "задач" in exported_text.lower()


@pytest.mark.skipif(not MAKET_RPD.is_file(), reason="Layout maket missing")
@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample RPD missing")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_and_export_rpd_via_exporter(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LAYOUT_DIR", str(ROOT / "Layout"))

    from app.database import engine

    await engine.dispose()
    await seed_layout_templates()
    from app.services.template_manager import list_templates

    templates = await list_templates()
    rpd_template = next(t for t in templates if "РПД" in t.name)

    data = SAMPLE_RPD.read_bytes()
    _, sections = await DocumentParser().parse_docx(data)
    sections_data = {
        s.section_name: s.content
        for s in sections
        if s.content and s.content.strip()
    }

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    output_path, _stats = await Exporter.export_document(
        document_id=str(uuid.uuid4()),
        sections_data=sections_data,
        template_id=str(rpd_template.id),
        output_dir=str(export_dir),
    )
    output = Path(output_path)
    assert output.is_file()
    doc = Document(output)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert len(text) > 1000
    assert "университет" in text.lower()


def test_layout_templates_configured() -> None:
    names = {name for _, name in LAYOUT_TEMPLATES}
    assert "РПД FGOS 3 (макет)" in names
    assert "ФОС FGOS 3 (макет)" in names
