"""Интеграция архива с макетами Layout/."""

from __future__ import annotations

import uuid

import pytest
from docx import Document

from app.models import PlanDiscipline, Program
from app.services.constructor_export import export_constructor_via_layout
from app.services.layout_bootstrap import ensure_layout_files
from app.services.program_constructor import save_constructor_data
from app.services.template_manager import seed_layout_templates


@pytest.mark.asyncio
async def test_archive_layout_export_practice(db_session, tmp_path, monkeypatch) -> None:
    layout_root = tmp_path / "Layout"
    monkeypatch.setenv("LAYOUT_DIR", str(layout_root))
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))

    from app.database import engine

    await engine.dispose()

    ensure_layout_files()
    registered = await seed_layout_templates()
    assert "РПп FGOS 3 (макет)" in registered

    discipline = PlanDiscipline(code="Б2.В.01", name="Учебная практика")
    program = Program(id=uuid.uuid4(), plan_discipline_id=discipline.id, program_kind="practice")
    save_constructor_data(
        program,
        {
            "section_11_annotation": "Общие положения",
            "section_31_stages": [{"title": "Этап 1", "hours": "40", "competencies": "ОПК-1"}],
        },
    )

    result = await export_constructor_via_layout(
        db_session,
        program,
        discipline,
        export_dir=str(tmp_path / "exports"),
    )
    assert result is not None
    docx_bytes, stats = result
    assert len(docx_bytes) > 500
    assert stats.get("mode") in {"headings", "assemble", "placeholders"}
    doc = Document(__import__("io").BytesIO(docx_bytes))
    text = "\n".join(p.text for p in doc.paragraphs).lower()
    assert "практик" in text or "этап" in text or "общие" in text
