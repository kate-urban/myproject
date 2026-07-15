"""Тесты инкрементального экспорта в исходный DOCX."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from docx import Document

from app.services.document_storage import save_document_source
from app.services.export_incremental import changed_sections_for_export
from app.services.exporter import Exporter
from app.services.parser import DocumentParser

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RPD = ROOT / "samples" / "B1_O_01_07_Proektnaya_deyatelnost_k55.docx"
MAKET_RPD = ROOT / "Layout" / "Maket_RPd_FGOS_3.docx"


@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample RPD missing")
def test_changed_sections_only_when_content_differs() -> None:
    data = SAMPLE_RPD.read_bytes()
    _, sections = asyncio.run(DocumentParser().parse_docx(data))
    baseline = {s.section_name: s.content or "" for s in sections}
    assert baseline

    doc_id = uuid.uuid4()
    source_path = save_document_source(doc_id, data)

    unchanged = changed_sections_for_export(source_path, baseline)
    assert unchanged == {}

    edited = dict(baseline)
    first_name = next(iter(baseline))
    edited[first_name] = (baseline[first_name] or "") + "<p> правка</p>"
    changed = changed_sections_for_export(source_path, edited)
    assert list(changed.keys()) == [first_name]


@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample RPD missing")
@pytest.mark.skipif(not MAKET_RPD.is_file(), reason="Layout maket missing")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_uses_original_incremental_mode(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LAYOUT_DIR", str(ROOT / "Layout"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))

    from app.services.template_manager import list_templates, seed_layout_templates

    await seed_layout_templates()
    templates = await list_templates()
    rpd_template = next(t for t in templates if "РПД" in t.name)

    data = SAMPLE_RPD.read_bytes()
    doc_id = uuid.uuid4()
    source_path = save_document_source(doc_id, data)
    _, sections = await DocumentParser().parse_docx(data)
    sections_data = {
        s.section_name: s.content for s in sections if s.content and s.content.strip()
    }

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    _, stats = await Exporter.export_document(
        document_id=str(doc_id),
        sections_data=sections_data,
        template_id=str(rpd_template.id),
        output_dir=str(export_dir),
        sections_order=[s.section_name for s in sections],
        source_path=source_path,
        incremental=True,
    )

    assert stats["mode"] == "original"
    assert stats.get("sections_changed", 0) == 0

    out = Document(export_dir / f"{doc_id}.docx")
    source = Document(source_path)
    assert len(out.paragraphs) == len(source.paragraphs)


@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample RPD missing")
@pytest.mark.skipif(not MAKET_RPD.is_file(), reason="Layout maket missing")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_patches_only_edited_sections(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LAYOUT_DIR", str(ROOT / "Layout"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))

    from app.services.template_manager import list_templates, seed_layout_templates

    await seed_layout_templates()
    templates = await list_templates()
    rpd_template = next(t for t in templates if "РПД" in t.name)

    data = SAMPLE_RPD.read_bytes()
    doc_id = uuid.uuid4()
    source_path = save_document_source(doc_id, data)
    _, sections = await DocumentParser().parse_docx(data)
    sections_data = {
        s.section_name: s.content for s in sections if s.content and s.content.strip()
    }
    target_name = next(iter(sections_data))
    marker = "ИНКРЕМЕНТАЛЬНАЯ_ПРАВКА"
    sections_data[target_name] = sections_data[target_name] + f"<p>{marker}</p>"

    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    output_path, stats = await Exporter.export_document(
        document_id=str(doc_id),
        sections_data=sections_data,
        template_id=str(rpd_template.id),
        output_dir=str(export_dir),
        source_path=source_path,
        incremental=True,
    )

    assert stats["mode"] == "original"
    assert stats.get("sections_changed") == 1
    exported_text = "\n".join(p.text for p in Document(output_path).paragraphs)
    assert marker in exported_text
