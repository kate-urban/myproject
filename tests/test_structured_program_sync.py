"""Синхронизация ZUV из RpdExtract."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import STRUCTURED_RPD_ENABLED
from app.models import PlanDiscipline, Program
from app.models_tz import ProgramZuv
from app.services.importers import StudyPlanImporter
from app.services.rpd_extractor import RpdExtract
from app.services.structured_program_sync import sync_program_from_extract

DESIGN_PLX = Path(__file__).resolve().parents[1] / "samples" / "M540401-2026.plx"

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.skipif(not STRUCTURED_RPD_ENABLED, reason="STRUCTURED_RPD_ENABLED=false")
async def test_sync_allows_multiple_zuv_per_indicator_type(db_session) -> None:
    if not DESIGN_PLX.is_file():
        pytest.skip("M540401-2026.plx missing")

    plan = await StudyPlanImporter().import_file(DESIGN_PLX, db_session)
    discipline = (
        await db_session.execute(
            select(PlanDiscipline).where(PlanDiscipline.study_plan_id == plan.id).limit(1)
        )
    ).scalar_one()
    program = Program(id=uuid.uuid4(), plan_discipline_id=discipline.id, status="uploaded")
    db_session.add(program)
    discipline.program = program
    await db_session.flush()

    rpd = RpdExtract(
        discipline_code=discipline.code,
        section2_zuv_by_indicator={
            "УК-5.1": [
                "знать первая формулировка",
                "знать вторая формулировка",
            ],
        },
    )

    await sync_program_from_extract(db_session, program, rpd, discipline=discipline)
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(ProgramZuv)
            .where(ProgramZuv.program_id == program.id)
            .order_by(ProgramZuv.row_order)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert all(row.indicator_code == "УК-5.1" and row.zuv_type == "know" for row in rows)

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(ProgramZuv)
            .where(
                ProgramZuv.program_id == program.id,
                ProgramZuv.indicator_code == "УК-5.1",
                ProgramZuv.zuv_type == "know",
            )
        )
    ).scalar_one()
    assert count == 2
