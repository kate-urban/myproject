"""Проверка извлечения РПД на примерах из samples/ИЛИП."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from app.services.doc_converter import convert_doc_file_to_docx
from app.services.rpd_extractor import extract_rpd

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
ILIP_DIR = next((p for p in SAMPLES.rglob("*") if p.is_dir() and "05.03.06" in p.name), None)
ILIP_DOCS = sorted(ILIP_DIR.glob("B1_*.doc"))[:8] if ILIP_DIR else []


def _extract_doc(src: Path):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        ascii_src = td_path / "sample.doc"
        shutil.copy2(src, ascii_src)
        dst = td_path / "sample.docx"
        convert_doc_file_to_docx(ascii_src, dst)
        return extract_rpd(dst.read_bytes(), src.name)


@pytest.mark.skipif(not ILIP_DOCS, reason="ILIP samples not found")
@pytest.mark.parametrize("doc_path", ILIP_DOCS, ids=[p.stem[:24] for p in ILIP_DOCS])
def test_ilip_extract_core_fields(doc_path: Path) -> None:
    rpd = _extract_doc(doc_path)
    assert rpd.discipline_code
    assert rpd.hours_total is not None or rpd.volume.contact is not None


@pytest.mark.skipif(not ILIP_DOCS, reason="ILIP samples not found")
def test_ilip_matematika_zuv_and_matrix() -> None:
    src = next((p for p in ILIP_DOCS if "Matematika" in p.name), None)
    if src is None:
        pytest.skip("Matematika sample missing")
    rpd = _extract_doc(src)
    assert len(rpd.topics31_zuv_phrases) >= 4, "З/У/В в таблице 3.1 не извлечены"
    assert len(rpd.matrix_36_rows) >= 1, "Матрица 3.6 не найдена"
    assert len(rpd.sr_questions) >= 1, "Вопросы СР не извлечены"
    assert rpd.topics31_assessments, "Формы аттестации не извлечены из табл. 1.3"
    forms = {(a["form_type"], a.get("semester")) for a in rpd.topics31_assessments}
    assert ("zachet", 1) in forms or ("exam", 2) in forms
    assert "ОПК-1.1" in rpd.section2_zuv_by_indicator, "З/У/В ОПК-1.1 не извлечены из §2"


@pytest.mark.skipif(not ILIP_DIR, reason="ILIP samples not found")
def test_ilip_inostranny_section2_and_assessments() -> None:
    src = next(ILIP_DIR.glob("*Inostranny*"))
    rpd = _extract_doc(src)
    assert rpd.section2_zuv_by_indicator, "§2 (таблица компетенций) не извлечён"
    assert any(key.startswith("УК-4") for key in rpd.section2_zuv_by_indicator), "УК-4 не найдены"
    forms = {(a["form_type"], a.get("semester")) for a in rpd.topics31_assessments}
    assert ("zachet_graded", 1) in forms
    assert ("exam", 3) in forms
