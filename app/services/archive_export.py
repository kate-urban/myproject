"""Сборка архивного тома: опись, Word/PDF через Layout/, duplex, поле 30 мм (P3)."""

from __future__ import annotations

import io
import uuid

import fitz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PlanDiscipline, Profile, Program, StudyPlan
from app.models_tz import ArchiveVolume, ArchiveVolumeItem
from app.services.archive_typography import (
    TYPOGRAPHY,
    append_pdf_to_document,
    build_missing_program_pdf,
    build_text_pdf,
    insert_blank_page,
    insert_page_number,
)
from app.services.layout_archive_export import build_program_archive_parts_layout
from app.utils.plan_title import form_display_label

ARCHIVE_LEFT_MM = TYPOGRAPHY.binding_left_mm

CERTIFICATION_TEMPLATE = """ЛИСТ-ЗАВЕРИТЕЛЬ

Перечень документов, помещённых в архивный том:

{title}

Направление подготовки: {direction_code} — {direction_name}
Профиль: {profile_name}
Год набора: {year}
Форма обучения: {form}

Настоящим подтверждаю, что документы перечислены в описи тома,
пронумерованы и прошиты. Левое поле для переплёта — 30 мм.

Дата: _________________          Подпись: _________________
"""


async def load_study_plan_for_archive(
    db: AsyncSession,
    plan_id: uuid.UUID,
) -> StudyPlan | None:
    """StudyPlan с profile.direction — без lazy-load в async."""
    result = await db.execute(
        select(StudyPlan)
        .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
        .where(StudyPlan.id == plan_id)
    )
    return result.scalar_one_or_none()


def build_certification_text(volume: ArchiveVolume, plan: StudyPlan | None = None) -> str:
    if volume.cover_text and volume.cover_text.strip():
        return volume.cover_text.strip()
    direction_code = "—"
    direction_name = "—"
    profile_name = "—"
    year: str | int = "—"
    form = "—"
    if plan is not None:
        profile = getattr(plan, "profile", None)
        if profile is not None:
            profile_name = profile.name or "—"
            direction = getattr(profile, "direction", None)
            if direction is not None:
                direction_code = direction.code or "—"
                direction_name = direction.name or "—"
        if plan.year is not None:
            year = plan.year
        if plan.form:
            form = form_display_label(plan.form)
    return CERTIFICATION_TEMPLATE.format(
        title=volume.title,
        direction_code=direction_code,
        direction_name=direction_name,
        profile_name=profile_name,
        year=year,
        form=form,
    ).strip()


def build_inventory_text(
    volume: ArchiveVolume,
    items: list[ArchiveVolumeItem],
    disciplines: dict[uuid.UUID, PlanDiscipline],
    programs: dict[uuid.UUID, Program] | None = None,
) -> str:
    lines = [
        "ОПИСЬ документов архивного тома",
        f"«{volume.title}»",
        "",
        "№ | Шифр | Наименование | Листов | Страницы",
        "-" * 60,
    ]
    for index, item in enumerate(sorted(items, key=lambda row: row.row_order), start=1):
        program = (programs or {}).get(item.program_id) or item.program
        discipline = disciplines.get(program.plan_discipline_id) if program else None
        code = discipline.code if discipline else "—"
        name = discipline.name if discipline else "—"
        sheets = item.sheet_count if item.sheet_count is not None else "—"
        page_range = "—"
        if item.page_start and item.page_end:
            page_range = (
                str(item.page_start)
                if item.page_start == item.page_end
                else f"{item.page_start}–{item.page_end}"
            )
        lines.append(f"{index} | {code} | {name} | {sheets} | {page_range}")
    lines.extend(["", f"Всего документов: {len(items)}", "", "Лист-заверитель — стр. 1"])
    return "\n".join(lines)


def count_pdf_pages(data: bytes) -> int:
    doc = fitz.open(stream=data, filetype="pdf")
    count = len(doc)
    doc.close()
    return count


def _missing_program_reasons(program: Program) -> list[str]:
    reasons: list[str] = []
    if not program.document_id and not program.constructor_json:
        reasons.append("РПД не загружена и конструктор пуст")
    elif not program.document_id:
        reasons.append("для практики/ГИА нет данных в конструкторе")
    else:
        reasons.append("не удалось собрать PDF (проверьте разделы документа и LibreOffice)")
    if not program.fos_document_id:
        reasons.append("ФОС не загружена (необязательно для всех дисциплин)")
    return reasons


async def build_volume_pdf_bytes(db: AsyncSession, volume_id: uuid.UUID) -> tuple[bytes, list[str]]:
    result = await db.execute(
        select(ArchiveVolume)
        .options(
            selectinload(ArchiveVolume.items).selectinload(ArchiveVolumeItem.program),
        )
        .where(ArchiveVolume.id == volume_id)
    )
    volume = result.scalar_one_or_none()
    if volume is None:
        raise ValueError("Том не найден")

    plan = await load_study_plan_for_archive(db, volume.study_plan_id)
    if plan is None:
        raise ValueError("Учебный план не найден")
    if not volume.cover_text:
        volume.cover_text = build_certification_text(volume, plan)

    duplex = bool(getattr(volume, "duplex_enabled", True))

    disc_result = await db.execute(
        select(PlanDiscipline).where(PlanDiscipline.study_plan_id == plan.id)
    )
    disciplines = {row.id: row for row in disc_result.scalars().all()}

    merged = fitz.open()
    page_num = 0
    export_warnings: list[str] = []

    def append_pdf_bytes(data: bytes, *, pad_before: bool = False) -> int:
        nonlocal page_num
        if pad_before and duplex and page_num > 0 and page_num % 2 == 0:
            insert_blank_page(merged)
            page_num += 1
            insert_page_number(merged[page_num - 1], page_num, duplex=duplex)

        start_idx = merged.page_count
        pages_added = append_pdf_to_document(merged, data)
        for offset in range(pages_added):
            page_num += 1
            insert_page_number(merged[start_idx + offset], page_num, duplex=duplex)
        return pages_added

    cover_pdf = build_text_pdf(build_certification_text(volume, plan).splitlines())
    append_pdf_bytes(cover_pdf)

    if not volume.inventory_text:
        program_ids = [item.program_id for item in volume.items]
        programs_map = {}
        if program_ids:
            programs_map = {
                row.id: row
                for row in (
                    await db.execute(select(Program).where(Program.id.in_(program_ids)))
                ).scalars().all()
            }
        volume.inventory_text = build_inventory_text(
            volume, volume.items, disciplines, programs_map
        )

    inv_pdf = build_text_pdf(volume.inventory_text.splitlines())
    append_pdf_bytes(inv_pdf, pad_before=duplex)

    for item in sorted(volume.items, key=lambda row: row.row_order):
        program = item.program
        if program is None:
            continue
        discipline = disciplines.get(program.plan_discipline_id)
        if discipline is None:
            continue

        if duplex and page_num > 0 and page_num % 2 == 0:
            insert_blank_page(merged)
            page_num += 1

        item.page_start = page_num + 1
        sheets = 0

        archive_parts = await build_program_archive_parts_layout(db, program, discipline)
        if archive_parts:
            for _label, pdf_data in archive_parts:
                sheets += append_pdf_bytes(pdf_data, pad_before=duplex)
        else:
            export_warnings.append(
                f"{discipline.code} {discipline.name}: программа не собрана "
                f"({'; '.join(_missing_program_reasons(program))})"
            )
            placeholder = build_missing_program_pdf(
                discipline.code or "—",
                discipline.name or "—",
                _missing_program_reasons(program),
            )
            sheets += append_pdf_bytes(placeholder, pad_before=duplex)

        item.sheet_count = sheets or None
        item.page_end = page_num if sheets else item.page_start

    if duplex and page_num % 2 == 1:
        insert_blank_page(merged)
        page_num += 1
        insert_page_number(merged[page_num - 1], page_num, duplex=duplex)

    program_ids = [item.program_id for item in volume.items]
    programs_map = {
        row.id: row
        for row in (
            await db.execute(select(Program).where(Program.id.in_(program_ids)))
        ).scalars().all()
    } if program_ids else {}
    volume.inventory_text = build_inventory_text(
        volume, list(volume.items), disciplines, programs_map
    )

    if len(merged) >= 2:
        inv_pdf = build_text_pdf(volume.inventory_text.splitlines())
        merged.delete_page(1)
        inv_doc = fitz.open(stream=inv_pdf, filetype="pdf")
        merged.insert_pdf(inv_doc, start_at=1)
        inv_doc.close()
        insert_page_number(merged[1], 2, duplex=duplex)

    out = io.BytesIO()
    merged.save(out, deflate=True, garbage=4)
    merged.close()
    return out.getvalue(), export_warnings


from app.services.constructor_export import build_constructor_sections as _constructor_sections  # noqa: E402

# re-export for tests
from app.services.archive_typography import apply_archive_margins  # noqa: E402

__all__ = [
    "ARCHIVE_LEFT_MM",
    "apply_archive_margins",
    "build_certification_text",
    "build_inventory_text",
    "build_volume_pdf_bytes",
    "count_pdf_pages",
    "load_study_plan_for_archive",
    "_constructor_sections",
]
