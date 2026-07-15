"""Тесты печатного экспорта: паспорт и подписи в DOCX."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from app.services.export_docx_signatures import overlay_docx_signatures
from app.services.export_finalize import finalize_export_docx
from app.services.export_passport import fill_passport_tables
from app.services.rpd_extractor import RpdExtract

ROOT = Path(__file__).resolve().parents[1]
MAKET = ROOT / "Layout" / "Maket_RPd_FGOS_3.docx"


class _Sig:
    def __init__(self, role: str, full_name: str, png_path: str | None = None):
        self.role = role
        self.full_name = full_name
        self.png_path = png_path
        self.is_active = True


@pytest.mark.skipif(not MAKET.is_file(), reason="Layout maket missing")
def test_fill_passport_tables_on_maket(tmp_path: Path) -> None:
    out = tmp_path / "out.docx"
    doc = Document(MAKET)
    doc.save(out)

    rpd = RpdExtract(
        discipline_code="Б1.О.01.07",
        discipline_name="Проектная деятельность",
        direction_code="05.03.06",
        profile_name="Экология",
        credits=2.0,
        authors=["Иванов И.И.", "Петров П.П."],
    )
    doc = Document(out)
    stats = fill_passport_tables(
        doc,
        rpd=rpd,
        discipline_code="Б1.О.01.07",
        discipline_name="Проектная деятельность",
        direction_code="05.03.06",
        direction_name="Экология и природопользование",
        profile_name="Экология",
        department_name="Кафедра лесной таксации",
        credits=2.0,
        control_label="экзамен",
        authors=["Иванов И.И.", "Петров П.П."],
    )
    doc.save(out)

    assert stats["discipline"] >= 1
    assert stats["direction"] >= 1
    saved = Document(out)
    body = "\n".join(p.text for p in saved.paragraphs)
    tables = " ".join(c.text for t in saved.tables for r in t.rows for c in r.cells)
    assert "Б1.О.01.07" in tables or "Б1.О.01.07" in body
    assert "05.03.06" in tables


@pytest.mark.skipif(not MAKET.is_file(), reason="Layout maket missing")
def test_finalize_maket_inserts_signature_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPECTED_DIRECTOR", "Директор Тестов Т.Т.")
    monkeypatch.setenv("EXPECTED_DISCIPLINE_HEAD", "Руководитель Программ П.П.")
    monkeypatch.setenv("EXPORT_FILL_SIGNATURES", "true")
    monkeypatch.setenv("EXPORT_FILL_REAPPROVAL", "false")

    out = tmp_path / "print.docx"
    doc = Document(MAKET)
    doc.save(out)

    stats = finalize_export_docx(
        str(out),
        rpd=RpdExtract(
            discipline_code="Б1.О.01.07",
            discipline_name="Тест",
            direction_code="05.03.06",
            credits=2.0,
        ),
        discipline_code="Б1.О.01.07",
        discipline_name="Тест",
        direction_code="05.03.06",
        direction_name="Экология",
        profile_name="Профиль",
        signatures=[
            _Sig("director", "Директор Тестов Т.Т."),
            _Sig("discipline_head", "Руководитель Программ П.П."),
        ],
    )
    assert stats.get("passport_filled", 0) >= 1

    saved = Document(out)
    table0 = saved.tables[0].rows[0].cells[0].text + saved.tables[0].rows[0].cells[2].text
    assert "Тестов" in table0 or "Директор" in table0
