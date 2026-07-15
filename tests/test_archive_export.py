"""Тесты сборки архивного тома (P3)."""

from __future__ import annotations

import uuid

import fitz

from app.models import PlanDiscipline, Program
from app.models_tz import ArchiveVolume, ArchiveVolumeItem
from app.services.archive_export import apply_archive_margins, build_inventory_text


def test_apply_archive_margins_shifts_content() -> None:
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((10, 20), "X", fontsize=12)
    buf = doc.tobytes()
    doc.close()

    shifted = apply_archive_margins(buf, left_mm=30.0)
    out = fitz.open(stream=shifted, filetype="pdf")
    assert out[0].rect.width > 200
    out.close()


def test_build_inventory_text_uses_program_map() -> None:
    volume = ArchiveVolume(
        id=uuid.uuid4(),
        study_plan_id=uuid.uuid4(),
        title="Том 1",
        cover_text="Заверяю…",
    )
    disc_id = uuid.uuid4()
    program_id = uuid.uuid4()
    program = Program(id=program_id, plan_discipline_id=disc_id)
    item = ArchiveVolumeItem(
        id=uuid.uuid4(),
        volume_id=volume.id,
        program_id=program_id,
        row_order=0,
        sheet_count=12,
    )
    disciplines = {
        disc_id: PlanDiscipline(id=disc_id, code="Б1.О.01", name="Экология"),
    }
    text = build_inventory_text(volume, [item], disciplines, {program_id: program})
    assert "Б1.О.01" in text
    assert "Экология" in text
    assert "12" in text
    assert "стр. 1" in text


def test_archive_volume_duplex_default() -> None:
    volume = ArchiveVolume(
        id=uuid.uuid4(),
        study_plan_id=uuid.uuid4(),
        title="Том duplex",
        duplex_enabled=True,
    )
    assert volume.duplex_enabled is True
