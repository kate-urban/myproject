"""Синхронизация RpdExtract → program_structured_rpd (additive к HTML)."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Program, ProgramStructuredRpd
from app.services.rpd_extractor import RpdExtract


def build_structured_payload(rpd: RpdExtract) -> dict:
    from dataclasses import asdict

    data = asdict(rpd)
    return {
        "passport": {
            "discipline_code": rpd.discipline_code,
            "discipline_name": rpd.discipline_name,
            "direction_code": rpd.direction_code,
            "profile_name": rpd.profile_name,
            "approval_year": rpd.approval_year,
        },
        "volume": data.get("volume"),
        "competencies": rpd.competencies,
        "section2_zuv": rpd.section2_zuv_by_indicator,
        "topics31_zuv": rpd.topics31_zuv_phrases,
        "topic_numbers": rpd.topic_numbers,
        "topic_names": {str(k): v for k, v in rpd.topic_names.items()},
        "topic_titles_bold": rpd.topic_titles_bold,
        "sr_rows": rpd.sr_rows,
        "sr_questions": rpd.sr_questions,
        "matrix_36": rpd.matrix_36_rows,
        "assessments_31": rpd.topics31_assessments,
    }


async def sync_structured_rpd(
    db: AsyncSession,
    program: Program,
    rpd: RpdExtract,
) -> None:
    payload = build_structured_payload(rpd)
    raw = json.dumps(payload, ensure_ascii=False)

    result = await db.execute(
        select(ProgramStructuredRpd).where(
            ProgramStructuredRpd.program_id == program.id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(
            ProgramStructuredRpd(
                id=uuid.uuid4(),
                program_id=program.id,
                payload_json=raw,
            )
        )
    else:
        row.payload_json = raw
