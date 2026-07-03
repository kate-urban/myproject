"""
Шаг 0: анализ образцов в samples/ → docs/field_map_data.json

Запуск из корня проекта:
    venv\\Scripts\\python.exe scripts/analyze_samples.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
OUTPUT = ROOT / "docs" / "field_map_data.json"


def classify_table(table) -> str:
    if not table.rows:
        return "empty"
    hdr = " ".join(c.text.lower().replace("\n", " ") for c in table.rows[0].cells)
    full = hdr
    if len(table.rows) > 1:
        full += " " + " ".join(c.text.lower() for c in table.rows[1].cells)
    patterns = [
        ("passport_signatures", ["согласовано", "утвержда"]),
        ("passport_discipline", ["дисциплин", "практик"]),
        ("passport_direction", ["направлен", "подготовк"]),
        ("passport_profile", ["профиль", "направленност"]),
        ("passport_department", ["кафедр"]),
        ("volume_13", ["вид учебных занятий"]),
        ("topics_31", ["темы (разделы)", "трудоемкость"]),
        ("topics_31_detailed", ["№ темы", "лекции"]),
        ("sr_35", ["самостоятельной работы", "трудо"]),
        ("competencies", ["компетенц", "индикатор"]),
        ("zuv", ["знать", "уметь", "владеть"]),
        ("literature", ["литератур", "источник"]),
        ("mto", ["материально", "техническ"]),
        ("fos_assessment", ["оценочн", "контролируем"]),
        ("grading_criteria", ["критерии оценки", "балл"]),
    ]
    for code, kws in patterns:
        hits = sum(1 for k in kws if k in full)
        if hits >= min(2, len(kws)):
            return code
    if "№ темы" in full or "№ п/п" in full:
        return "topics_table"
    return "other"


def analyze_excel() -> dict:
    import openpyxl

    result = {}
    for path in sorted(SAMPLES.glob("*.xlsx")):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        info = {
            "sheets_count": len(wb.sheetnames),
            "sheets": wb.sheetnames,
            "key_sheets": {},
        }
        targets = {"План", "ПланСвод", "Компетенции", "Компетенции(2)", "Лист1", "Свод"}
        for sn in wb.sheetnames:
            if sn not in targets:
                continue
            ws = wb[sn]
            rows = []
            for i, row in enumerate(ws.iter_rows(max_row=25, values_only=True), 1):
                cells = [str(c)[:60] if c is not None else "" for c in row[:20]]
                if any(c.strip() for c in cells):
                    rows.append({"row": i, "cells": cells})
            info["key_sheets"][sn] = rows[:10]
        result[path.name] = info
        wb.close()
    return result


def analyze_docx() -> dict:
    from docx import Document

    result = {}
    for path in sorted(SAMPLES.glob("*.docx")):
        doc = Document(path)
        styles: dict[str, int] = {}
        for p in doc.paragraphs:
            if p.text.strip() and p.style:
                sn = p.style.name
                styles[sn] = styles.get(sn, 0) + 1
        tables = []
        for ti, t in enumerate(doc.tables):
            hdr = " | ".join(
                c.text.strip()[:35].replace("\n", " ") for c in t.rows[0].cells[:4]
            )
            tables.append(
                {
                    "idx": ti,
                    "rows": len(t.rows),
                    "cols": len(t.columns),
                    "type": classify_table(t),
                    "header": hdr[:120],
                }
            )
        if path.name.startswith("FOS_"):
            doc_type = "fos"
        elif path.name.startswith("B2_"):
            doc_type = "practice"
        else:
            doc_type = "rpd"
        result[path.name] = {
            "doc_type": doc_type,
            "tables_count": len(doc.tables),
            "top_styles": sorted(styles.items(), key=lambda x: -x[1])[:10],
            "tables": tables,
        }
    return result


def main() -> int:
    try:
        excel = analyze_excel()
        docx = analyze_docx()
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"excel": excel, "docx": docx}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written {OUTPUT.relative_to(ROOT)}")
    print(f"  Excel: {len(excel)} files, DOCX: {len(docx)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
