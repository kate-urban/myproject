"""
Импорт учебного плана в PostgreSQL.

Пример:
    venv\\Scripts\\python.exe scripts/import_study_plan.py samples/M540401-2026.plx
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import func, select, text

load_dotenv(ROOT / ".env")

from app.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import PlanDiscipline, StudyPlan  # noqa: E402
from app.services.importers import StudyPlanImporter  # noqa: E402


async def main_async(path: Path) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_discipline_code VARCHAR(32)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_hours_total INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_credits DOUBLE PRECISION"
            )
        )
        for ddl in (
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_discipline_name VARCHAR",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_direction_code VARCHAR(16)",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_profile_name VARCHAR",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_department_code VARCHAR(16)",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_competencies TEXT",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_extract_json TEXT",
        ):
            await conn.execute(text(ddl))

    importer = StudyPlanImporter()
    dto = importer.read_dto(path)

    print(f"Файл: {path.name}")
    print(
        f"  {dto.direction_code} «{dto.direction_name}» / "
        f"«{dto.profile_name}», {dto.year}, {dto.form}"
    )
    print(f"  Дисциплин: {len(dto.disciplines)}")

    async with AsyncSessionLocal() as db:
        plan = await importer.import_file(path, db)

        count = await db.scalar(
            select(func.count())
            .select_from(PlanDiscipline)
            .where(PlanDiscipline.study_plan_id == plan.id)
        )
        print(f"OK: study_plan_id={plan.id}, записей в plan_disciplines={count}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_study_plan.py <path-to.plx|.xlsx>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 1

    asyncio.run(main_async(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
