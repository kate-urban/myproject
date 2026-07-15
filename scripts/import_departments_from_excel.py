"""Массовый импорт кафедр из Excel в ref_departments."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.database import AsyncSessionLocal
from app.services.department_import import parse_departments_from_xlsx, persist_department_rows


async def import_departments(path: Path, *, dry_run: bool = False) -> tuple[int, int, int]:
    rows, warnings = parse_departments_from_xlsx(path)
    for warning in warnings:
        print(f"⚠ {warning}")

    if not rows:
        print("Нечего импортировать.")
        return 0, 0, 0

    if dry_run:
        for row in sorted(rows, key=lambda r: (r.code, r.name)):
            print(f"+ [{row.code}] {row.name}  (лист {row.source_sheet})")
        return len(rows), 0, len(rows)

    import app.models  # noqa: F401 — регистрация ORM-моделей

    async with AsyncSessionLocal() as db:
        result = await persist_department_rows(db, rows)
        return result["added"], result["skipped"], result["total"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Импорт кафедр из Excel (код + название) в справочник ref_departments.",
    )
    parser.add_argument(
        "xlsx",
        type=Path,
        help="Путь к .xlsx (свод УП, отчёт 7.2 «Справочник» и т.п.)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет добавлено, без записи в БД",
    )
    args = parser.parse_args()

    added, skipped, total = asyncio.run(import_departments(args.xlsx, dry_run=args.dry_run))
    action = "Будет добавлено" if args.dry_run else "Добавлено"
    print(f"\n{action}: {added}, пропущено (уже есть): {skipped}, уникальных пар в файле: {total}")


if __name__ == "__main__":
    main()
