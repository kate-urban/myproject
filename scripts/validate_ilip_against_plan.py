#!/usr/bin/env python3
"""Импорт B050306-2022.plx и пакетная сверка РПД из samples/ИЛИП."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

PLAN_FILE = ROOT / "samples" / "B050306-2022.plx"
ILIP_DIR = next((p for p in (ROOT / "samples").rglob("*") if p.is_dir() and "05.03.06" in p.name), None)


async def run_batch(limit: int | None = None) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models import Document, PlanDiscipline, Profile, StudyPlan
    from app.services.doc_converter import doc_batch_converter
    from app.services.importers import StudyPlanImporter
    from app.services.rpd_linker import link_document_to_program
    from app.services.validation import validate_program, DEFAULT_RULE_IDS

    if not PLAN_FILE.is_file():
        raise FileNotFoundError(PLAN_FILE)
    if ILIP_DIR is None:
        raise FileNotFoundError("ILIP samples folder not found")

    docs = sorted(ILIP_DIR.glob("*.doc"))
    if limit:
        docs = docs[:limit]

    importer = StudyPlanImporter()
    summary: dict = {
        "plan": PLAN_FILE.name,
        "ilip_dir": ILIP_DIR.name,
        "total_docs": len(docs),
        "linked": 0,
        "not_in_plan": 0,
        "errors": 0,
        "passed": 0,
        "failed": 0,
        "items": [],
        "rule_failures": Counter(),
    }

    async with AsyncSessionLocal() as db:
        plan = await importer.import_file(PLAN_FILE, db)
        await db.commit()

        plan_loaded = (
            await db.execute(
                select(StudyPlan)
                .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
                .where(StudyPlan.id == plan.id)
            )
        ).scalar_one()

        with doc_batch_converter() as converter:
            for doc_path in docs:
                item: dict = {"file": doc_path.name}
                try:
                    raw = doc_path.read_bytes()
                    file_bytes, filename = converter.to_docx_bytes(raw, doc_path.name)
                    document_id = uuid.uuid4()
                    db.add(Document(id=document_id, filename=filename, doc_type="rpd"))
                    await db.flush()

                    link = await link_document_to_program(
                        db,
                        document_id=document_id,
                        study_plan_id=plan.id,
                        file_bytes=file_bytes,
                        filename=filename,
                    )
                    await db.commit()

                    if not link.linked:
                        summary["not_in_plan"] += 1
                        item.update(
                            linked=False,
                            reason=link.reason,
                            code=link.discipline_code,
                        )
                        summary["items"].append(item)
                        continue

                    summary["linked"] += 1
                    discipline = (
                        await db.execute(
                            select(PlanDiscipline)
                            .options(
                                selectinload(PlanDiscipline.program),
                                selectinload(PlanDiscipline.competencies),
                                selectinload(PlanDiscipline.assessments),
                            )
                            .where(
                                PlanDiscipline.study_plan_id == plan.id,
                                PlanDiscipline.code == link.discipline_code,
                            )
                        )
                    ).scalar_one()

                    report = validate_program(
                        plan_loaded,
                        discipline,
                        discipline.program,
                        rule_ids=DEFAULT_RULE_IDS,
                    )
                    failed = [
                        r.rule_id
                        for r in report.results
                        if not r.skipped and r.severity == "critical" and not r.passed
                    ]
                    for rule_id in failed:
                        summary["rule_failures"][rule_id] += 1

                    if report.passed:
                        summary["passed"] += 1
                    else:
                        summary["failed"] += 1

                    item.update(
                        linked=True,
                        code=link.discipline_code,
                        passed=report.passed,
                        failed_rules=failed,
                    )
                except Exception as exc:
                    summary["errors"] += 1
                    item["error"] = str(exc)[:200]
                summary["items"].append(item)
                print(
                    f"{item.get('code', '?'):12} | "
                    f"{'OK' if item.get('passed') else 'FAIL' if item.get('linked') else item.get('reason', 'err')[:20]:20} | "
                    f"{doc_path.name[:45]}"
                )

        summary["plan_id"] = str(plan.id)
        summary["rule_failures"] = dict(summary["rule_failures"])

    out = ROOT / "docs" / "ilip_validation_report.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    summary = asyncio.run(run_batch(limit=limit))
    print(
        f"\nИтого: linked={summary['linked']} passed={summary['passed']} "
        f"failed={summary['failed']} not_in_plan={summary['not_in_plan']} errors={summary['errors']}"
    )
    print("Топ ошибок:", summary.get("rule_failures"))
    print(f"Отчёт: docs/ilip_validation_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
