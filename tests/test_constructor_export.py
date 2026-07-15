"""Тесты экспорта конструктора ГИА/практик."""

from __future__ import annotations

import uuid
import zipfile
from io import BytesIO

from docx import Document

from app.models import PlanDiscipline, Program
from app.services.constructor_export import (
    build_constructor_docx_bytes,
    build_constructor_pdf_bytes,
    build_constructor_sections,
    export_filename,
)
from app.services.program_constructor import save_constructor_data


def _gia_program() -> tuple[Program, PlanDiscipline]:
    discipline = PlanDiscipline(
        id=uuid.uuid4(),
        code="Б3.В.01",
        name="Государственная итоговая атестация",
    )
    program = Program(
        id=uuid.uuid4(),
        plan_discipline_id=discipline.id,
        program_kind="gia",
    )
    save_constructor_data(
        program,
        {
            "section_11_annotation": "Общие положения ГИА",
            "section_12_goals": "Цели и задачи",
            "section_13_competencies": [
                {"indicator": "ОПК-1.1", "competency": "ОПК-1", "evidence": "Выпускная работа"},
            ],
            "section_22_topic_fund": [
                {"topic": "Экологический мониторинг", "supervisor": "Иванов И.И.", "department": "42"},
            ],
            "section_31_criteria": [
                {
                    "criterion": "Качество оформления",
                    "level_high": "Без замечаний",
                    "level_mid": "Незначительные",
                    "level_low": "Существенные",
                }
            ],
            "section_32_gek": [
                {"role": "Председатель", "fio": "Петров П.П.", "position": "профessor"},
            ],
            "fos_competencies": [{"code": "ОПК-1.1", "title": "Применяет методы мониторинга"}],
            "fos_os_list": [{"tool": "Защита ВКР", "form": "устная", "weight": "100%"}],
            "fos_criteria": [
                {
                    "criterion": "Доклад",
                    "level_high": "Отлично",
                    "level_mid": "Хорошо",
                    "level_low": "Удовл.",
                }
            ],
            "fos_questions": "Вопросы по теме ВКР",
        },
    )
    return program, discipline


def test_gia_constructor_sections_include_tables() -> None:
    program, discipline = _gia_program()
    sections = build_constructor_sections(program, discipline)
    labels = [label for label, _ in sections]
    assert any("матрица" in label.lower() for label in labels)
    assert any("фонд тем" in label.lower() for label in labels)
    assert any("гэк" in label.lower() for label in labels)


def test_gia_fos_sections_separate() -> None:
    program, discipline = _gia_program()
    fos_sections = build_constructor_sections(program, discipline, fos_only=True)
    assert fos_sections
    assert all("ФОС" in label for label, _ in fos_sections)


def test_gia_docx_export_is_valid_zip() -> None:
    program, discipline = _gia_program()
    data = build_constructor_docx_bytes(program, discipline)
    assert zipfile.is_zipfile(BytesIO(data))
    doc = Document(BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ГИА" in text or "матрица" in text.lower() or "Общие положения" in text


def test_gia_pdf_export_non_empty() -> None:
    program, discipline = _gia_program()
    pdf = build_constructor_pdf_bytes(program, discipline)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 200


def test_export_filename_gia() -> None:
    discipline = PlanDiscipline(code="Б3.В.01", name="ГИА")
    assert export_filename(discipline).endswith("_GIA.docx")
    assert export_filename(discipline, fos=True).startswith("FOS_")
