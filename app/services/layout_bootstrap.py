"""Генерация минимальных макетов Word в Layout/, если файлов ещё нет в репозитории."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from app.services.archive_typography import apply_typography_to_docx
from app.services.template_manager import LAYOUT_TEMPLATES, layout_dir


def _add_title_block(doc: Document, *, doc_title: str, subtitle: str = "") -> None:
    for text, size, bold in (
        ("Федеральное государственное бюджетное образовательное учреждение", 11, False),
        ("высшего образования", 11, False),
        ("", 6, False),
        (doc_title.upper(), 14, True),
        ("", 8, False),
    ):
        p = doc.add_paragraph(text)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if p.runs:
            p.runs[0].font.size = Pt(size)
            p.runs[0].bold = bold
    if subtitle:
        p = doc.add_paragraph(subtitle)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")
    p = doc.add_paragraph("Шифр {{DISCIPLINE_CODE}}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph("{{DISCIPLINE_NAME}}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")


def _add_numbered_headings(doc: Document, headings: list[str]) -> None:
    for heading in headings:
        p = doc.add_paragraph(heading)
        if p.runs:
            p.runs[0].bold = True


def _save_template(path: Path, doc: Document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    apply_typography_to_docx(doc)
    doc.save(str(path))


def _build_rpd_template(path: Path) -> None:
    doc = Document()
    _add_title_block(doc, doc_title="Рабочая программа дисциплины")
    _add_numbered_headings(
        doc,
        [
            "1. Цель и задачи дисциплины",
            "2. Место дисциплины в структуре образовательной программы",
            "3. Требования к результатам освоения дисциплины",
            "3.1. Содержание дисциплины",
            "4. Объём дисциплины и виды учебной работы",
            "5. Формы контроля",
            "6. Учебно-методическое обеспечение",
            "9. Список литературы",
            "11. Материально-техническое обеспечение",
            "13. Аннотация",
        ],
    )
    _save_template(path, doc)


def _build_rpp_template(path: Path) -> None:
    doc = Document()
    _add_title_block(doc, doc_title="Рабочая программа практики")
    _add_numbered_headings(
        doc,
        [
            "1.1. Общие положения",
            "1.1. Цели и задачи практики",
            "1.3. Объем практики",
            "3.1. Содержание и этапы практики",
            "3.2. Самостоятельная работа обучающихся и фонды оценочных средств",
        ],
    )
    _save_template(path, doc)


def _build_fos_discipline_template(path: Path) -> None:
    doc = Document()
    _add_title_block(doc, doc_title="Фонд оценочных средств", subtitle="дисциплины")
    _add_numbered_headings(
        doc,
        [
            "Перечень компетенций, формируемых в результате освоения дисциплины (модуля)",
            "Перечень оценочных средств",
            "Критерии оценивания",
            "Примерные вопросы и задания",
        ],
    )
    _save_template(path, doc)


def _build_fos_practice_template(path: Path) -> None:
    doc = Document()
    _add_title_block(doc, doc_title="Фонд оценочных средств", subtitle="практики")
    _add_numbered_headings(
        doc,
        [
            "Перечень компетенций, формируемых в результате освоения практики",
            "Перечень оценочных средств",
            "Критерии оценивания",
            "Примерные вопросы и задания",
        ],
    )
    _save_template(path, doc)


def _build_gia_template(path: Path) -> None:
    doc = Document()
    _add_title_block(doc, doc_title="Государственная итоговая аттестация")
    _add_numbered_headings(
        doc,
        [
            "1.1. Общие положения",
            "1.2. Цели и задачи государственной итоговой аттестации",
            "1.3. Матрица компетенций",
            "2.1. Требования к выпускной квалификационной работе",
            "2.2. Фонд тем выпускных квалификационных работ",
            "3.1. Критерии оценивания результатов освоения программы",
            "3.2. Состав государственной экзаменационной комиссии",
            "4. Литература",
        ],
    )
    _save_template(path, doc)


def _build_fos_gia_template(path: Path) -> None:
    doc = Document()
    _add_title_block(
        doc,
        doc_title="Фонд оценочных средств",
        subtitle="государственной итоговой аттестации",
    )
    _add_numbered_headings(
        doc,
        [
            "Перечень компетенций, формируемых в результате освоения дисциплины (модуля)",
            "Перечень оценочных средств",
            "Критерии оценивания",
            "Примерные вопросы и задания",
        ],
    )
    _save_template(path, doc)


_BUILDERS = {
    "Maket_RPd_FGOS_3.docx": _build_rpd_template,
    "Maket_RPp_FGOS_3.docx": _build_rpp_template,
    "Maket_FOSd_FGOS_3.docx": _build_fos_discipline_template,
    "Maket_FOSp_FGOS_3.docx": _build_fos_practice_template,
    "B3_01_Gosudarstvennaya_itogovaya_attestatsia_k21.docx": _build_gia_template,
    "FOS_B3_01_Gosudarstvennaya_itogovaya_attestatsia_k21.docx": _build_fos_gia_template,
}


def ensure_layout_files() -> list[str]:
    """Создаёт отсутствующие .docx в Layout/ (bootstrap для dev/CI)."""
    root = layout_dir()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for filename, _display in LAYOUT_TEMPLATES:
        builder = _BUILDERS.get(filename)
        if builder is None:
            continue
        target = root / filename
        if target.is_file():
            continue
        builder(target)
        if target.is_file():
            created.append(filename)
    return created
