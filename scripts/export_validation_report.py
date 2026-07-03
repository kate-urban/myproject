#!/usr/bin/env python3
"""Экспорт сводного отчёта валидации УП ↔ РПД ↔ ФОС в JSON/HTML."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models import PlanDiscipline, StudyPlan
from app.services.validation import validate_study_plan, validate_study_plan_fos
from app.services.validation.report_export import (
    build_validation_report_payload,
    payload_to_json,
    render_validation_report_html,
)


async def _load_plan(session, plan_id: UUID) -> StudyPlan | None:
    result = await session.execute(
        select(StudyPlan)
        .options(selectinload(StudyPlan.profile))
        .where(StudyPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        return None
    await session.refresh(plan, ["profile"])
    await session.refresh(plan.profile, ["direction"])
    return plan


async def _load_disciplines(session, plan_id: UUID) -> list[PlanDiscipline]:
    result = await session.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    return list(result.scalars().all())


async def export_report(plan_id: UUID, output: Path, fmt: str) -> None:
    async with AsyncSessionLocal() as session:
        plan = await _load_plan(session, plan_id)
        if plan is None:
            raise SystemExit(f"Study plan not found: {plan_id}")

        disciplines = await _load_disciplines(session, plan_id)
        rpd_report = validate_study_plan(plan, disciplines)
        fos_report = validate_study_plan_fos(plan, disciplines)
        payload = build_validation_report_payload(
            plan,
            rpd_report=rpd_report,
            fos_report=fos_report,
        )

    if fmt == "html":
        content = render_validation_report_html(payload)
    else:
        content = payload_to_json(payload)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"Written: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export validation report")
    parser.add_argument("plan_id", help="UUID учебного плана")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file (default: exports/validation_<id>.json|html)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "html"),
        default="json",
        help="Report format",
    )
    args = parser.parse_args()

    try:
        plan_uuid = UUID(args.plan_id)
    except ValueError:
        print("Invalid plan_id UUID", file=sys.stderr)
        return 2

    output = args.output
    if output is None:
        output = ROOT / "exports" / f"validation_{plan_uuid}.{args.format}"

    asyncio.run(export_report(plan_uuid, output, args.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
