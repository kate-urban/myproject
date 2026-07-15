"""Экспорт конструктора РПп/ГИА в Word и PDF."""

from __future__ import annotations

import io
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Mm, Pt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document as DocumentModel
from app.models import PlanDiscipline, Program, Section
from app.config import (
    DEFAULT_FOS_GIA_TEMPLATE_NAME,
    DEFAULT_FOSP_TEMPLATE_NAME,
    DEFAULT_GIA_TEMPLATE_NAME,
    DEFAULT_RPP_TEMPLATE_NAME,
)
from app.services.document_reextract import build_docx_bytes_from_sections
from app.services.archive_typography import TYPOGRAPHY
from app.services.blocking_pool import run_blocking
from app.services.exporter import Exporter
from app.services.pdf_export import build_pdf_from_sections, convert_docx_to_pdf
from app.services.program_constructor import (
    load_constructor_data,
    program_kind_for,
    template_for_kind,
)
from app.services.template_manager import get_template_by_name, seed_layout_templates

FOS_GIA_FIELD_PREFIX = "fos_"

CONSTRUCTOR_LAYOUT_TEMPLATE: dict[tuple[str, bool], str] = {
    ("gia", False): DEFAULT_GIA_TEMPLATE_NAME,
    ("gia", True): DEFAULT_FOS_GIA_TEMPLATE_NAME,
    ("practice", False): DEFAULT_RPP_TEMPLATE_NAME,
    ("practice", True): DEFAULT_FOSP_TEMPLATE_NAME,
}

# Заголовки разделов для сопоставления с макетами Layout/
LAYOUT_HEADINGS: dict[str, dict[str, str]] = {
    "gia": {
        "section_11_annotation": "1.1. Общие положения",
        "section_12_goals": "1.2. Цели и задачи государственной итоговой атестации",
        "section_13_competencies": "1.3. Матрица компетенций",
        "section_21_thesis": "2.1. Требования к выпускной квалификационной работе",
        "section_22_topic_fund": "2.2. Фонд тем выпускных квалификационных работ",
        "section_31_criteria": "3.1. Критерии оценивания результатов освоения программы",
        "section_32_gek": "3.2. Состав государственной экзаменационной комиссии",
        "literature": "4. Литература",
    },
    "practice": {
        "section_11_annotation": "1.1. Общие положения",
        "section_11_goals": "1.1. Цели и задачи практики",
        "section_13_volume": "1.3. Объем практики",
        "section_31_stages": "3.1. Содержание и этапы практики",
        "section_32_sr": "3.2. Самостоятельная работа обучающихся и фонды оценочных средств",
    },
    "gia_fos": {
        "fos_competencies": "Перечень компетенций, формируемых в результате освоения дисциплины (модуля)",
        "fos_os_list": "Перечень оценочных средств",
        "fos_criteria": "Критерии оценивания",
        "fos_questions": "Примерные вопросы и задания",
    },
    "practice_fos": {
        "fos_competencies": "Перечень компетенций, формируемых в результате освоения практики",
        "fos_os_list": "Перечень оценочных средств",
        "fos_criteria": "Критерии оценивания",
        "fos_questions": "Примерные вопросы и задания",
    },
}


def _escape_html(value: object) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _table_html(field: dict[str, Any], rows: list) -> str:
    cols = field.get("columns") or []
    if not cols or not rows:
        return ""
    header = "".join(f"<th>{_escape_html(col['label'])}</th>" for col in cols)
    body = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = "".join(f"<td>{_escape_html(row.get(col['key'], ''))}</td>" for col in cols)
        body.append(f"<tr>{cells}</tr>")
    if not body:
        return ""
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_constructor_sections(
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
    for_layout: bool = False,
) -> list[tuple[str, str]]:
    kind = program.program_kind or program_kind_for(discipline)
    template = template_for_kind(kind)
    if template is None:
        return []

    heading_map_key = f"{kind}_fos" if fos_only else kind
    heading_map = LAYOUT_HEADINGS.get(heading_map_key, {}) if for_layout else {}

    data = load_constructor_data(program)
    sections: list[tuple[str, str]] = []
    for field in template.get("fields", []):
        key = field["key"]
        if fos_only:
            if not key.startswith(FOS_GIA_FIELD_PREFIX):
                continue
        elif key.startswith(FOS_GIA_FIELD_PREFIX):
            continue

        value = data.get(key)
        section_title = heading_map.get(key, field["label"]) if for_layout else field["label"]
        if field.get("type") == "textarea" and value:
            paragraphs = "".join(
                f"<p>{_escape_html(line)}</p>" for line in str(value).splitlines() if line.strip()
            )
            if paragraphs:
                sections.append((section_title, paragraphs))
        elif field.get("type") == "table" and isinstance(value, list) and value:
            html = _table_html(field, value)
            if html:
                sections.append((section_title, html))

    if not sections and data and not fos_only:
        sections.append(
            (discipline.name, f"<pre>{_escape_html(json.dumps(data, ensure_ascii=False, indent=2))}</pre>")
        )
    return sections


async def _resolve_layout_template(
    db: AsyncSession,
    kind: str,
    *,
    fos_only: bool,
):
    template_name = CONSTRUCTOR_LAYOUT_TEMPLATE.get((kind, fos_only))
    if not template_name:
        return None
    template = await get_template_by_name(db, template_name)
    if template is not None:
        return template
    await seed_layout_templates()
    return await get_template_by_name(db, template_name)


async def export_constructor_via_layout(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
    export_dir: str | None = None,
) -> tuple[bytes, dict] | None:
    """Сборка DOCX через макет из Layout/ (Exporter)."""
    kind = program.program_kind or program_kind_for(discipline)
    template = await _resolve_layout_template(db, kind, fos_only=fos_only)
    if template is None:
        return None

    sections = build_constructor_sections(
        program, discipline, fos_only=fos_only, for_layout=True
    )
    if not sections:
        return None

    sections_data = {name: content for name, content in sections}
    sections_order = [name for name, _ in sections]
    out_dir = export_dir or tempfile.mkdtemp(prefix="constructor_export_")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    doc_type = "fos" if fos_only else kind
    output_path, stats = await Exporter.export_document(
        document_id=str(program.id),
        sections_data=sections_data,
        template_id=str(template.id),
        output_dir=out_dir,
        sections_order=sections_order,
        doc_type=doc_type,
        template_name=template.name,
    )
    return Path(output_path).read_bytes(), stats


async def build_constructor_docx_bytes_async(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
) -> bytes:
    layout = await export_constructor_via_layout(db, program, discipline, fos_only=fos_only)
    if layout is not None:
        return layout[0]
    return build_constructor_docx_bytes(program, discipline, fos_only=fos_only)


def build_constructor_docx_bytes(
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
) -> bytes:
    sections = build_constructor_sections(program, discipline, fos_only=fos_only)
    if not sections:
        kind = program.program_kind or program_kind_for(discipline)
        title = "ФОС ГИА" if fos_only else ("Программа ГИА" if kind == "gia" else "Программа практики")
        sections = [(title, f"<p>{_escape_html(discipline.name)}</p>")]
    return build_docx_bytes_from_sections(sections)


def build_constructor_docx_with_margins(
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
    left_mm: float = TYPOGRAPHY.binding_left_mm,
    raw_bytes: bytes | None = None,
) -> bytes:
    raw = raw_bytes if raw_bytes is not None else build_constructor_docx_bytes(
        program, discipline, fos_only=fos_only
    )
    doc = Document(io.BytesIO(raw))
    for section in doc.sections:
        section.left_margin = Mm(left_mm)
        section.right_margin = Mm(TYPOGRAPHY.margin_right_mm)
        section.top_margin = Mm(TYPOGRAPHY.margin_top_mm)
        section.bottom_margin = Mm(TYPOGRAPHY.margin_bottom_mm)
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def docx_bytes_to_pdf_bytes(docx_bytes: bytes, *, title: str = "export") -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        docx_path = Path(tmp) / f"{title}.docx"
        docx_path.write_bytes(docx_bytes)
        pdf_path = convert_docx_to_pdf(docx_path)
        if pdf_path and pdf_path.is_file():
            return pdf_path.read_bytes()

        sections_doc = Document(io.BytesIO(docx_bytes))
        pairs: list[tuple[str, str]] = []
        current_title = title
        current_body: list[str] = []
        for paragraph in sections_doc.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.runs and paragraph.runs[0].bold:
                if current_body:
                    pairs.append(
                        (
                            current_title,
                            "".join(f"<p>{_escape_html(line)}</p>" for line in current_body),
                        )
                    )
                    current_body = []
                current_title = text
            else:
                current_body.append(text)
        if current_body:
            pairs.append(
                (current_title, "".join(f"<p>{_escape_html(line)}</p>" for line in current_body))
            )
        if not pairs:
            pairs = [(title, "<p></p>")]

        out_pdf = Path(tmp) / f"{title}.pdf"
        build_pdf_from_sections(title=title, sections=pairs, output_path=out_pdf)
        return out_pdf.read_bytes()


async def docx_bytes_to_pdf_bytes_async(
    docx_bytes: bytes, *, title: str = "export"
) -> bytes:
    return await run_blocking(docx_bytes_to_pdf_bytes, docx_bytes, title=title)


def build_constructor_pdf_bytes(
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
    docx_bytes: bytes | None = None,
) -> bytes:
    if docx_bytes is not None:
        return docx_bytes_to_pdf_bytes(docx_bytes, title=discipline.code or "constructor")

    sections = build_constructor_sections(program, discipline, fos_only=fos_only)
    if sections:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = Path(tmp.name)
        build_pdf_from_sections(
            title=discipline.name,
            sections=sections,
            output_path=pdf_path,
        )
        data = pdf_path.read_bytes()
        pdf_path.unlink(missing_ok=True)
        return data
    docx = build_constructor_docx_bytes(program, discipline, fos_only=fos_only)
    return docx_bytes_to_pdf_bytes(docx, title=discipline.code or "constructor")


async def build_constructor_pdf_bytes_async(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    *,
    fos_only: bool = False,
) -> bytes:
    layout = await export_constructor_via_layout(db, program, discipline, fos_only=fos_only)
    if layout is not None:
        return await docx_bytes_to_pdf_bytes_async(
            layout[0], title=discipline.code or "constructor"
        )
    return await run_blocking(
        build_constructor_pdf_bytes,
        program,
        discipline,
        fos_only=fos_only,
    )


async def document_section_pairs(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> list[tuple[str, str]]:
    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    )
    return [(row.section_name, row.content or "") for row in result.scalars().all()]


async def build_document_pdf_bytes(
    db: AsyncSession,
    document_id: uuid.UUID,
    *,
    fallback_title: str = "document",
) -> bytes | None:
    doc = await db.get(DocumentModel, document_id)
    if doc is None:
        return None
    pairs = await document_section_pairs(db, document_id)
    if not pairs:
        return None
    docx_bytes = build_docx_bytes_from_sections(pairs)
    try:
        return await docx_bytes_to_pdf_bytes_async(docx_bytes, title=fallback_title)
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = Path(tmp.name)
        plain = [(name, content if content.strip().startswith("<") else f"<p>{_escape_html(content)}</p>") for name, content in pairs]
        await run_blocking(
            build_pdf_from_sections,
            title=fallback_title,
            sections=plain,
            output_path=pdf_path,
        )
        data = pdf_path.read_bytes()
        pdf_path.unlink(missing_ok=True)
        return data


async def build_program_archive_parts(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
) -> list[tuple[str, bytes]]:
    """Части архива: (метка, pdf_bytes) — Word/конструктор + ФОС."""
    parts: list[tuple[str, bytes]] = []
    bucket = program_kind_for(discipline)

    if program.document_id:
        pdf = await build_document_pdf_bytes(
            db,
            program.document_id,
            fallback_title=discipline.code or "rpd",
        )
        if pdf:
            parts.append(("document", pdf))
    elif program.constructor_json:
        parts.append(
            (
                "constructor",
                await build_constructor_pdf_bytes_async(db, program, discipline),
            )
        )

    if program.fos_document_id:
        pdf = await build_document_pdf_bytes(
            db,
            program.fos_document_id,
            fallback_title=f"FOS_{discipline.code or 'fos'}",
        )
        if pdf:
            parts.append(("fos", pdf))
    elif bucket == "gia" and program.constructor_json:
        data = load_constructor_data(program)
        if any(key.startswith(FOS_GIA_FIELD_PREFIX) and data.get(key) for key in data):
            parts.append(
                (
                    "fos_constructor",
                    await build_constructor_pdf_bytes_async(
                        db, program, discipline, fos_only=True
                    ),
                )
            )
    return parts


def gia_has_fos_section(program: Program) -> bool:
    if program.program_kind != "gia":
        return False
    data = load_constructor_data(program)
    return any(key.startswith(FOS_GIA_FIELD_PREFIX) and data.get(key) for key in data)


def export_filename(discipline: PlanDiscipline, *, fos: bool = False) -> str:
    code = (discipline.code or "program").replace("/", "-")
    if fos:
        return f"FOS_{code}.docx"
    kind = discipline.code or ""
    if kind.upper().startswith("Б3"):
        return f"{code}_GIA.docx"
    return f"{code}_RPP.docx"
