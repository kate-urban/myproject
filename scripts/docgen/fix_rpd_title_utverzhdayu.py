#!/usr/bin/env python3
"""Починка титула РПД: слева «Согласовано» (директор), справа «Утверждаю» (ОПОП)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from docx import Document

from scripts.docgen.maket_layouts import RPD_TITLE_DIRECTOR_CELL, RPD_TITLE_HEAD_CELL

TEMPLATE = ROOT / "templates" / "tagged" / "Maket_RPd_FGOS_3_tagged.docx"


def fix_title_table(doc: Document) -> None:
    row = doc.tables[0].rows[0]
    row.cells[0].text = RPD_TITLE_DIRECTOR_CELL
    if len(row.cells) > 2:
        row.cells[2].text = RPD_TITLE_HEAD_CELL


def main() -> None:
    if not TEMPLATE.is_file():
        raise SystemExit(f"Не найден: {TEMPLATE}")
    doc = Document(str(TEMPLATE))
    fix_title_table(doc)
    doc.save(str(TEMPLATE))
    print(f"Обновлён титул: {TEMPLATE}")


if __name__ == "__main__":
    main()
