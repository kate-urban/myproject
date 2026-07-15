"""Конвертация .doc → .docx."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.services.doc_converter import convert_doc_file_to_docx

SAMPLE_DOC = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "ИЛИП  с 2021 05.03.06"
    / "B1_O_01_Inostranny_yazyk_k4.doc"
)


@pytest.mark.skipif(not SAMPLE_DOC.is_file(), reason="sample .doc not found")
def test_convert_doc_file_to_docx(tmp_path) -> None:
    src = tmp_path / "sample.doc"
    dst = tmp_path / "sample.docx"
    shutil.copy(SAMPLE_DOC, src)
    convert_doc_file_to_docx(src, dst)
    assert dst.is_file()
    assert dst.stat().st_size > 1000
    from docx import Document

    doc = Document(str(dst))
    assert doc.paragraphs or doc.tables
