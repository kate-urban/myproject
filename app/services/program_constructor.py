"""Упрощённый конструктор РПп / ГИА (ТЗ модуль 3–4)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlanDiscipline, Program
from app.utils.discipline_bucket import classify_discipline_bucket

PRACTICE_TEMPLATE: dict[str, Any] = {
    "kind": "practice",
    "fields": [
        {"key": "annotation", "label": "Аннотация", "type": "textarea"},
        {"key": "goals", "label": "Цели практики", "type": "textarea"},
        {"key": "tasks", "label": "Задачи практики", "type": "textarea"},
        {
            "key": "stages",
            "label": "Этапы практики",
            "type": "table",
            "columns": [
                {"key": "title", "label": "Этап"},
                {"key": "hours", "label": "Часы"},
                {"key": "competencies", "label": "Компетенции"},
            ],
        },
        {"key": "mto_text", "label": "МТО и ресурсное обеспечение", "type": "textarea"},
        {"key": "assessment", "label": "Формы и методы оценки", "type": "textarea"},
    ],
    "defaults": {
        "annotation": "",
        "goals": "",
        "tasks": "",
        "stages": [],
        "mto_text": "",
        "assessment": "",
    },
}

GIA_TEMPLATE: dict[str, Any] = {
    "kind": "gia",
    "fields": [
        {"key": "annotation", "label": "Аннотация", "type": "textarea"},
        {"key": "goals", "label": "Цели ГИА", "type": "textarea"},
        {"key": "thesis_requirements", "label": "Требования к ВКР", "type": "textarea"},
        {"key": "defense_procedure", "label": "Порядок защиты", "type": "textarea"},
        {"key": "competencies_text", "label": "Формируемые компетенции", "type": "textarea"},
        {"key": "criteria", "label": "Критерии оценки", "type": "textarea"},
    ],
    "defaults": {
        "annotation": "",
        "goals": "",
        "thesis_requirements": "",
        "defense_procedure": "",
        "competencies_text": "",
        "criteria": "",
    },
}


def program_kind_for(discipline: PlanDiscipline) -> str:
    bucket = classify_discipline_bucket(
        code=discipline.code,
        name=discipline.name,
        object_type=discipline.object_type,
    )
    if bucket == "gia":
        return "gia"
    if bucket == "practices":
        return "practice"
    return "discipline"


def template_for_kind(kind: str) -> dict[str, Any] | None:
    if kind == "practice":
        return PRACTICE_TEMPLATE
    if kind == "gia":
        return GIA_TEMPLATE
    return None


def load_constructor_data(program: Program) -> dict[str, Any]:
    if not program.constructor_json:
        return {}
    try:
        return json.loads(program.constructor_json)
    except json.JSONDecodeError:
        return {}


def save_constructor_data(program: Program, data: dict[str, Any]) -> None:
    program.constructor_json = json.dumps(data, ensure_ascii=False)
    program.status = "draft"


async def get_constructor_payload(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
) -> dict[str, Any]:
    kind = program.program_kind or program_kind_for(discipline)
    template = template_for_kind(kind)
    if template is None:
        return {
            "supported": False,
            "kind": kind,
            "message": "Конструктор доступен только для практик и ГИА",
        }
    stored = load_constructor_data(program)
    merged = {**template["defaults"], **stored}
    return {
        "supported": True,
        "program_id": str(program.id),
        "discipline_id": str(discipline.id),
        "discipline_code": discipline.code,
        "discipline_name": discipline.name,
        "kind": kind,
        "fields": template["fields"],
        "data": merged,
    }


async def save_constructor_payload(
    db: AsyncSession,
    program: Program,
    discipline: PlanDiscipline,
    data: dict[str, Any],
) -> dict[str, Any]:
    kind = program_kind_for(discipline)
    template = template_for_kind(kind)
    if template is None:
        raise ValueError("Конструктор недоступен для обычных дисциплин")

    program.program_kind = kind
    cleaned = {k: data.get(k, template["defaults"].get(k)) for k in template["defaults"]}
    save_constructor_data(program, cleaned)

    from app.models_tz import ProgramTopic

    if kind == "practice" and isinstance(cleaned.get("stages"), list):
        from sqlalchemy import delete

        await db.execute(delete(ProgramTopic).where(ProgramTopic.program_id == program.id))
        for order, stage in enumerate(cleaned["stages"]):
            if not isinstance(stage, dict):
                continue
            title = str(stage.get("title") or "").strip()
            if not title:
                continue
            db.add(
                ProgramTopic(
                    id=uuid.uuid4(),
                    program_id=program.id,
                    topic_number=str(order + 1),
                    title=title,
                    hours_sr=int(stage["hours"]) if str(stage.get("hours", "")).isdigit() else None,
                    row_order=order,
                )
            )

    await db.flush()
    return await get_constructor_payload(db, program, discipline)
