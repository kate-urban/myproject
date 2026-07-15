"""P3: сборка МТО из аудиторий и автогенерация аннотаций."""

from __future__ import annotations

import uuid
from html import escape

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PlanDiscipline, Profile, Program, Section, StudyPlan
from app.models_tz import ProgramMtoRoom, RefMtoRoom, RefPhrase
from app.services.program_constructor import (
    load_constructor_data,
    program_kind_for,
    save_constructor_data,
    template_for_kind,
)
from app.utils.plan_title import form_display_label


def _section_matches(name: str, *needles: str) -> bool:
    lowered = (name or "").lower()
    return any(needle in lowered for needle in needles)


def _plain_to_html(text: str) -> str:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    if not paragraphs:
        return "<p>—</p>"
    return "".join(f"<p>{escape(part)}</p>" for part in paragraphs)


async def get_active_phrase(db: AsyncSession, category: str) -> str | None:
    result = await db.execute(
        select(RefPhrase)
        .where(RefPhrase.category == category, RefPhrase.is_active.is_(True))
        .order_by(RefPhrase.version.desc())
    )
    row = result.scalars().first()
    return row.text if row else None


def format_mto_text(intro: str, rooms: list[RefMtoRoom]) -> str:
    lines = [intro.strip()] if intro.strip() else []
    if rooms:
        lines.append("")
        lines.append("Аудитории и ресурсы:")
        for index, room in enumerate(rooms, start=1):
            parts = [f"{index}. {room.code} — {room.name}"]
            if room.building:
                parts.append(f"({room.building})")
            line = " ".join(parts)
            if room.equipment and room.equipment.strip():
                line += f". Оборудование: {room.equipment.strip()}"
            lines.append(line)
    return "\n".join(lines).strip()


def _plan_context(plan: StudyPlan | None, discipline: PlanDiscipline) -> dict[str, str]:
    direction_code = "—"
    direction_name = "—"
    profile_name = "—"
    year = "—"
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
            year = str(plan.year)
        if plan.form:
            form = form_display_label(plan.form)
    credits = str(discipline.credits) if discipline.credits is not None else "—"
    return {
        "discipline_code": discipline.code or "—",
        "discipline_name": discipline.name or "—",
        "direction_code": direction_code,
        "direction_name": direction_name,
        "profile_name": profile_name,
        "year": year,
        "form": form,
        "credits": credits,
    }


def _render_template(template: str, ctx: dict[str, str]) -> str:
    try:
        return template.format(**ctx).strip()
    except KeyError:
        return template.strip()


async def build_annotation_suggestion(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    plan: StudyPlan | None,
) -> str:
    kind = program.program_kind or program_kind_for(discipline)
    if kind == "gia":
        category = "gia_annotation"
    elif kind == "practice":
        category = "practice_annotation"
    else:
        category = "discipline_annotation"

    phrase = await get_active_phrase(db, category)
    ctx = _plan_context(plan, discipline)
    if phrase:
        return _render_template(phrase, ctx)

    if kind == "gia":
        return (
            f"Государственная итоговая аттестация по направлению {ctx['direction_code']} "
            f"«{ctx['direction_name']}», профиль «{ctx['profile_name']}»."
        )
    if kind == "practice":
        return (
            f"Практика «{ctx['discipline_name']}» ({ctx['discipline_code']}) направлена "
            f"на формирование профессиональных компетенций обучающегося."
        )
    return (
        f"Дисциплина «{ctx['discipline_name']}» ({ctx['discipline_code']}) входит в программу "
        f"подготовки по направлению {ctx['direction_code']} «{ctx['direction_name']}», "
        f"профиль «{ctx['profile_name']}». Объём — {ctx['credits']} з.е."
    )


async def list_program_mto_rooms(db: AsyncSession, program_id: uuid.UUID) -> list[RefMtoRoom]:
    result = await db.execute(
        select(RefMtoRoom)
        .join(ProgramMtoRoom, ProgramMtoRoom.room_id == RefMtoRoom.id)
        .where(ProgramMtoRoom.program_id == program_id)
        .order_by(RefMtoRoom.code)
    )
    return list(result.scalars().all())


async def replace_program_mto_rooms(
    db: AsyncSession,
    program_id: uuid.UUID,
    room_ids: list[uuid.UUID],
) -> list[RefMtoRoom]:
    await db.execute(delete(ProgramMtoRoom).where(ProgramMtoRoom.program_id == program_id))
    rooms: list[RefMtoRoom] = []
    if room_ids:
        found = await db.execute(select(RefMtoRoom).where(RefMtoRoom.id.in_(room_ids)))
        rooms = list(found.scalars().all())
        for room in rooms:
            db.add(ProgramMtoRoom(program_id=program_id, room_id=room.id))
    await db.flush()
    return rooms


async def build_mto_suggestion(db: AsyncSession, program_id: uuid.UUID) -> str:
    rooms = await list_program_mto_rooms(db, program_id)
    intro = await get_active_phrase(db, "mto") or (
        "Материально-техническое обеспечение дисциплины соответствует требованиям программы."
    )
    return format_mto_text(intro, rooms)


async def _apply_text_to_document_section(
    db: AsyncSession,
    document_id: uuid.UUID,
    text: str,
    *needles: str,
) -> bool:
    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    )
    for section in result.scalars().all():
        if _section_matches(section.section_name or "", *needles):
            section.content = _plain_to_html(text)
            return True
    return False


async def apply_mto_text(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    text: str,
) -> dict[str, object]:
    kind = program.program_kind or program_kind_for(discipline)
    template = template_for_kind(kind)
    if template is not None:
        data = load_constructor_data(program)
        merged = {**template["defaults"], **data, "mto_text": text}
        save_constructor_data(program, merged)
        return {"target": "constructor", "field": "mto_text"}

    if program.document_id is None:
        raise ValueError("Нет документа РПД и конструктор недоступен")

    updated = await _apply_text_to_document_section(
        db,
        program.document_id,
        text,
        "материально-техн",
        "мто",
        "11.",
        "ресурсное обеспеч",
    )
    if not updated:
        raise ValueError("Раздел МТО (п.11) не найден в документе")
    return {"target": "document", "document_id": str(program.document_id)}


async def apply_annotation_text(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    text: str,
) -> dict[str, object]:
    kind = program.program_kind or program_kind_for(discipline)
    template = template_for_kind(kind)
    if template is not None:
        data = load_constructor_data(program)
        merged = {**template["defaults"], **data}
        merged["annotation"] = text
        if "section_11_annotation" in merged:
            merged["section_11_annotation"] = text
        save_constructor_data(program, merged)
        return {"target": "constructor", "field": "annotation"}

    if program.document_id is None:
        raise ValueError("Нет документа РПД и конструктор недоступен")

    updated = await _apply_text_to_document_section(
        db,
        program.document_id,
        text,
        "аннотац",
    )
    if not updated:
        raise ValueError("Раздел «Аннотация» не найден в документе")
    return {"target": "document", "document_id": str(program.document_id)}


async def load_program_with_discipline(
    db: AsyncSession, program_id: uuid.UUID
) -> tuple[Program, PlanDiscipline, StudyPlan | None]:
    result = await db.execute(
        select(Program)
        .options(
            selectinload(Program.discipline)
            .selectinload(PlanDiscipline.study_plan)
            .selectinload(StudyPlan.profile)
            .selectinload(Profile.direction)
        )
        .where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None or program.discipline is None:
        raise ValueError("Программа не найдена")
    plan = program.discipline.study_plan
    return program, program.discipline, plan
