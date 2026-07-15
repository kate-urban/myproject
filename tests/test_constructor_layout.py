"""Тесты экспорта конструктора через макеты Layout/."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from docx import Document

from app.models import PlanDiscipline, Program
from app.services.constructor_export import (
    build_constructor_sections,
    export_constructor_via_layout,
)
from app.services.layout_bootstrap import ensure_layout_files
from app.services.program_constructor import save_constructor_data
from app.services.template_manager import (
    LAYOUT_TEMPLATES,
    layout_dir,
    materialize_layout_docx,
    resolve_layout_file,
    seed_layout_templates,
)

ROOT = Path(__file__).resolve().parents[1]
MAKET_RPP = ROOT / "Layout" / "Maket_RPp_FGOS_3.docx"
MAKET_GIA = ROOT / "Layout" / "B3_01_Gosudarstvennaya_itogovaya_attestatsia_k21.docx"


def test_resolve_layout_file_by_stem() -> None:
    ensure_layout_files()
    preferred = LAYOUT_TEMPLATES[1][0]
    found = resolve_layout_file(preferred)
    if found is None:
        pytest.skip("Layout files not present")
    assert found.is_file()


@pytest.mark.skipif(not MAKET_RPP.is_file(), reason="Maket_RPp missing in Layout/")
def test_layout_sections_use_numbered_headings() -> None:
    ensure_layout_files()
    discipline = PlanDiscipline(code="Б2.В.01", name="Практика")
    program = Program(id=uuid.uuid4(), plan_discipline_id=discipline.id, program_kind="practice")
    save_constructor_data(
        program,
        {
            "section_11_annotation": "Аннотация практики",
            "section_31_stages": [{"title": "Этап 1", "hours": "40", "competencies": "ОПК-1"}],
        },
    )
    sections = build_constructor_sections(program, discipline, for_layout=True)
    assert sections
    assert sections[0][0].startswith("1.")


@pytest.mark.skipif(not MAKET_RPP.is_file(), reason="Maket_RPp missing in Layout/")
@pytest.mark.asyncio
async def test_export_practice_via_layout(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LAYOUT_DIR", str(ROOT / "Layout"))

    from app.database import engine

    await engine.dispose()
    ensure_layout_files()
    registered = await seed_layout_templates()
    if "РПп FGOS 3 (макет)" not in registered:
        pytest.skip("РПп template not registered from Layout/")

    discipline = PlanDiscipline(code="Б2.В.01", name="Учебная практика")
    program = Program(id=uuid.uuid4(), plan_discipline_id=discipline.id, program_kind="practice")
    save_constructor_data(
        program,
        {
            "section_11_annotation": "Общие положения учебной практики",
            "section_11_goals": "Цели и задачи практики",
            "section_31_stages": [
                {"title": "Ознакомительный этап", "hours": "72", "competencies": "ОПК-2.1"},
            ],
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
    doc = Document(__import__("io").BytesIO(docx_bytes))
    text = "\n".join(p.text for p in doc.paragraphs).lower()
    assert stats.get("mode") in {"headings", "assemble", "placeholders"}
    assert "практик" in text or "ознаком" in text


@pytest.mark.skipif(not MAKET_GIA.is_file(), reason="B3_01 GIA maket missing in Layout/")
@pytest.mark.asyncio
async def test_export_gia_via_layout(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LAYOUT_DIR", str(ROOT / "Layout"))

    from app.database import engine

    await engine.dispose()
    ensure_layout_files()
    registered = await seed_layout_templates()
    if "ГИА B3_01 (макет)" not in registered:
        pytest.skip("GIA template not registered")

    discipline = PlanDiscipline(code="Б3.В.01", name="ГИА")
    program = Program(id=uuid.uuid4(), plan_discipline_id=discipline.id, program_kind="gia")
    save_constructor_data(
        program,
        {
            "section_11_annotation": "Положения ГИА",
            "section_22_topic_fund": [
                {"topic": "Тема ВКР", "supervisor": "Иванов", "department": "21"},
            ],
        },
    )

    result = await export_constructor_via_layout(
        db_session,
        program,
        discipline,
        export_dir=str(tmp_path / "exports"),
    )
    assert result is not None
    docx_bytes, _stats = result
    doc = Document(__import__("io").BytesIO(docx_bytes))
    text = "\n".join(p.text for p in doc.paragraphs).lower()
    assert "итогов" in text or "тема" in text or "положен" in text
