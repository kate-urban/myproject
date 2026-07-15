"""Логика «основа → производная» из структуры UpVo (.plx)."""

from __future__ import annotations

from app.models import PlanDiscipline

IMPORTABLE_OBJECT_TYPES = frozenset({"2", "3", "6"})


def _main_cycle(identifier: str | None) -> str | None:
    if not identifier:
        return None
    return identifier.split(".")[0].upper()


def foundation_disciplines(
    target: PlanDiscipline,
    plan_disciplines: list[PlanDiscipline],
) -> list[PlanDiscipline]:
    """
    Дисциплины учебного плана, которые по структуре UpVo должны быть освоены раньше target.

    Правила (эталон M540401-2026.plx):
    - базовая часть (блок «базовая», напр. Б1.О) → основа для вариативной (Б1.В);
    - внутри одного цикла — все строки с меньшим row_order.
    """
    if (target.object_type or "") not in IMPORTABLE_OBJECT_TYPES:
        return []

    target_cycle = _main_cycle(getattr(target, "cycle_identifier", None))
    target_block = (getattr(target, "block_type", None) or "").strip().lower()
    foundations: list[PlanDiscipline] = []

    for item in plan_disciplines:
        if item.id == target.id:
            continue
        if (item.object_type or "") not in IMPORTABLE_OBJECT_TYPES:
            continue
        if item.row_order >= target.row_order:
            continue

        item_cycle = _main_cycle(getattr(item, "cycle_identifier", None))
        item_block = (getattr(item, "block_type", None) or "").strip().lower()

        if target_block == "вариативная" and item_block == "базовая":
            if target_cycle and item_cycle == target_cycle:
                foundations.append(item)
            continue

        if (
            target_block
            and item_block == target_block
            and getattr(item, "cycle_identifier", None)
            == getattr(target, "cycle_identifier", None)
        ):
            foundations.append(item)

    return sorted(foundations, key=lambda row: (row.row_order, row.code))
