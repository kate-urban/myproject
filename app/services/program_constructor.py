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
    "sections": ["1.1", "1.3", "3.1", "3.2"],
    "fields": [
        {"key": "section_11_annotation", "label": "1.1 Общие положения", "type": "textarea"},
        {"key": "section_11_goals", "label": "1.1 Цели и задачи практики", "type": "textarea"},
        {"key": "section_13_volume", "label": "1.3 Объём практики (таблица)", "type": "textarea"},
        {"key": "section_31_stages", "label": "3.1 Содержание (этапы)", "type": "table", "columns": [
            {"key": "title", "label": "Этап"},
            {"key": "hours", "label": "Часы/дни"},
            {"key": "competencies", "label": "Компетенции"},
        ]},
        {"key": "section_32_sr", "label": "3.2 Самостоятельная работа и оценка", "type": "textarea"},
        {"key": "annotation", "label": "Аннотация", "type": "textarea"},
        {"key": "goals", "label": "Цели практики", "type": "textarea"},
        {"key": "tasks", "label": "Задачи практики", "type": "textarea"},
        {"key": "stages", "label": "Этапы практики (legacy)", "type": "table", "columns": [
            {"key": "title", "label": "Этап"},
            {"key": "hours", "label": "Часы"},
            {"key": "competencies", "label": "Компетенции"},
        ]},
        {"key": "mto_text", "label": "МТО и ресурсное обеспечение", "type": "textarea"},
        {"key": "assessment", "label": "Формы и методы оценки", "type": "textarea"},
    ],
    "defaults": {
        "section_11_annotation": "",
        "section_11_goals": "",
        "section_13_volume": "",
        "section_31_stages": [],
        "section_32_sr": "",
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
    "sections": ["1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2"],
    "fields": [
        {"key": "section_11_annotation", "label": "1.1 Общие положения", "type": "textarea"},
        {"key": "section_12_goals", "label": "1.2 Цели и задачи ГИА", "type": "textarea"},
        {
            "key": "section_13_competencies",
            "label": "1.3 Матрица компетенций",
            "type": "table",
            "columns": [
                {"key": "indicator", "label": "Индикатор"},
                {"key": "competency", "label": "Компетенция"},
                {"key": "evidence", "label": "Доказательства достижения"},
            ],
        },
        {"key": "section_21_thesis", "label": "2.1 Требования к ВКР / НИР", "type": "textarea"},
        {
            "key": "section_22_topic_fund",
            "label": "2.2 Фонд тем ВКР",
            "type": "table",
            "columns": [
                {"key": "topic", "label": "Тема"},
                {"key": "supervisor", "label": "Руководитель"},
                {"key": "department", "label": "Кафедра"},
            ],
        },
        {
            "key": "section_31_criteria",
            "label": "3.1 Критерии оценки (3 уровня)",
            "type": "table",
            "columns": [
                {"key": "criterion", "label": "Критерий"},
                {"key": "level_high", "label": "Высокий"},
                {"key": "level_mid", "label": "Средний"},
                {"key": "level_low", "label": "Низкий"},
            ],
        },
        {
            "key": "section_32_gek",
            "label": "3.2 Состав ГЭК",
            "type": "table",
            "columns": [
                {"key": "role", "label": "Роль"},
                {"key": "fio", "label": "ФИО"},
                {"key": "position", "label": "Должность / организация"},
            ],
        },
        {"key": "annotation", "label": "Аннотация", "type": "textarea"},
        {"key": "goals", "label": "Цели ГИА", "type": "textarea"},
        {"key": "thesis_requirements", "label": "Требования к ВКР", "type": "textarea"},
        {"key": "defense_procedure", "label": "Порядок защиты", "type": "textarea"},
        {"key": "competencies_text", "label": "Формируемые компетенции (текст)", "type": "textarea"},
        {"key": "criteria", "label": "Критерии оценки (текст)", "type": "textarea"},
        {"key": "mto_text", "label": "МТО и ресурсное обеспечение", "type": "textarea"},
        {"key": "literature", "label": "Литература", "type": "textarea"},
        {"key": "fos_competencies", "label": "ФОС: формируемые компетенции", "type": "table", "columns": [
            {"key": "code", "label": "Код"},
            {"key": "title", "label": "Содержание"},
        ]},
        {"key": "fos_os_list", "label": "ФОС: оценочные средства", "type": "table", "columns": [
            {"key": "tool", "label": "Средство"},
            {"key": "form", "label": "Форма контроля"},
            {"key": "weight", "label": "Удельный вес"},
        ]},
        {"key": "fos_criteria", "label": "ФОС: критерии оценки (3 уровня)", "type": "table", "columns": [
            {"key": "criterion", "label": "Критерий"},
            {"key": "level_high", "label": "Высокий"},
            {"key": "level_mid", "label": "Средний"},
            {"key": "level_low", "label": "Низкий"},
        ]},
        {"key": "fos_questions", "label": "ФОС: вопросы / задания", "type": "textarea"},
    ],
    "defaults": {
        "section_11_annotation": "",
        "section_12_goals": "",
        "section_13_competencies": [],
        "section_21_thesis": "",
        "section_22_topic_fund": [],
        "section_31_criteria": [],
        "section_32_gek": [],
        "annotation": "",
        "goals": "",
        "thesis_requirements": "",
        "defense_procedure": "",
        "competencies_text": "",
        "criteria": "",
        "mto_text": "",
        "literature": "",
        "fos_competencies": [],
        "fos_os_list": [],
        "fos_criteria": [],
        "fos_questions": "",
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

    if kind == "gia":
        from sqlalchemy import delete

        from app.models_tz import ProgramLiterature, ProgramZuv

        topic_rows = cleaned.get("section_22_topic_fund") or cleaned.get("section_31_stages") or []
        if isinstance(topic_rows, list) and topic_rows:
            await db.execute(delete(ProgramTopic).where(ProgramTopic.program_id == program.id))
            for order, row in enumerate(topic_rows):
                if not isinstance(row, dict):
                    continue
                title = str(row.get("topic") or row.get("title") or "").strip()
                if not title:
                    continue
                db.add(
                    ProgramTopic(
                        id=uuid.uuid4(),
                        program_id=program.id,
                        topic_number=str(order + 1),
                        title=title,
                        row_order=order,
                    )
                )

        comp_rows = cleaned.get("section_13_competencies") or []
        if isinstance(comp_rows, list) and comp_rows:
            await db.execute(delete(ProgramZuv).where(ProgramZuv.program_id == program.id))
            zuv_order = 0
            for row in comp_rows:
                if not isinstance(row, dict):
                    continue
                indicator = str(row.get("indicator") or "").strip().upper()
                text = str(row.get("evidence") or row.get("competency") or "").strip()
                if not indicator or not text:
                    continue
                db.add(
                    ProgramZuv(
                        id=uuid.uuid4(),
                        program_id=program.id,
                        indicator_code=indicator,
                        zuv_type="know",
                        text=text,
                        row_order=zuv_order,
                    )
                )
                zuv_order += 1

        lit_text = str(cleaned.get("literature") or "").strip()
        if lit_text:
            await db.execute(
                delete(ProgramLiterature).where(ProgramLiterature.program_id == program.id)
            )
            for order, line in enumerate(line for line in lit_text.splitlines() if line.strip()):
                db.add(
                    ProgramLiterature(
                        id=uuid.uuid4(),
                        program_id=program.id,
                        citation=line.strip(),
                        lit_type="main",
                        row_order=order,
                    )
                )

    await db.flush()
    return await get_constructor_payload(db, program, discipline)
