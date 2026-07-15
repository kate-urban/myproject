"""Тесты сборки экспорта (шапка макета + всё содержимое)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from docx import Document

from app.services.export_assemble import assemble_document_from_sections, detect_template_kind
from app.services.exporter import Exporter
from app.services.parser import DocumentParser

ROOT = Path(__file__).resolve().parents[1]
MAKET_FOS = ROOT / "Layout" / "Maket_FOSd_FGOS_3.docx"
SAMPLE_RPD = ROOT / "samples" / "B1_O_01_07_Proektnaya_deyatelnost_k55.docx"


@pytest.mark.skipif(not MAKET_FOS.is_file(), reason="FOS maket missing")
def test_detect_fos_template() -> None:
    doc = Document(MAKET_FOS)
    assert detect_template_kind(doc) == "fos"


@pytest.mark.skipif(not MAKET_FOS.is_file(), reason="FOS maket missing")
@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample missing")
def test_assemble_puts_content_into_fos_maket() -> None:
    async def _sections() -> list[tuple[str, str]]:
        data = SAMPLE_RPD.read_bytes()
        _, sections = await DocumentParser().parse_docx(data)
        return [
            (s.section_name, s.content)
            for s in sections
            if s.content and s.content.strip()
        ][:5]

    ordered = asyncio.run(_sections())
    doc = Document(MAKET_FOS)
    before_len = sum(len(p.text) for p in doc.paragraphs)
    injected = assemble_document_from_sections(doc, ordered, template_kind="fos")
    after_len = sum(len(p.text) for p in doc.paragraphs)

    assert injected == len(ordered)
    text = "\n".join(p.text for p in doc.paragraphs).lower()
    assert "цел" in text or "дисциплин" in text


@pytest.mark.skipif(not MAKET_FOS.is_file(), reason="FOS maket missing")
@pytest.mark.skipif(not SAMPLE_RPD.is_file(), reason="sample missing")
@pytest.mark.integration
def test_fos_export_uses_assemble_mode(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LAYOUT_DIR", str(ROOT / "Layout"))

    async def _run() -> dict:
        from app.services.template_manager import list_templates, seed_layout_templates

        await seed_layout_templates()
        templates = await list_templates()
        fos_template = next(t for t in templates if "ФОС" in t.name)

        data = SAMPLE_RPD.read_bytes()
        _, sections = await DocumentParser().parse_docx(data)
        sections_data = {
            s.section_name: s.content for s in sections if s.content and s.content.strip()
        }
        sections_order = [s.section_name for s in sections]

        export_dir = tmp_path / "exports"
        export_dir.mkdir()
        _, stats = await Exporter.export_document(
            document_id="test-fos",
            sections_data=sections_data,
            template_id=str(fos_template.id),
            output_dir=str(export_dir),
            sections_order=sections_order,
            doc_type="fos",
            template_name=fos_template.name,
        )
        return stats

    stats = asyncio.run(_run())
    assert stats["mode"] == "assemble"
    assert stats["assembled"] >= 1
