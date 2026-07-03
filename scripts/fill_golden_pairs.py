"""Extract data from samples to help fill golden_pairs.yaml."""

from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
OUT = ROOT / "docs" / "_golden_extract.json"

PLX_FILES = [
    "B080301-LSTR-2026_plx.xlsx",
    "B080301-LSTR-2026oz_plx.xlsx",
    "B380304-2022_plx.xlsx",
]

DOCX_FILES = [
    "B1_O_01_07_Proektnaya_deyatelnost_k55.docx",
    "B1_V_01_03_Marketing_ekologicheskikh_produktov_k51.docx",
    "B1_V_02_05_Kompyuternye_tekhnologii_v_nauke_i_proizvodstve_k45.docx",
    "B2_O_03_P_Proizvodstvennaya_praktika_Proektnaya_praktika_k55.docx",
    "FOS_B1_O_13_Tekhnologii_programmirovania_k45.docx",
    "FOS_B1_O_23_Teoria_informatsii_dannye_znania_k45.docx",
    "FTD_01_Istoria_razvitia_nauki_i_tekhniki_k52.docx",
]

SEARCH_TERMS = [
    "01.07", "01.03", "02.05", "01.13", "01.23", "03(П)", "03(п)",
    "Проектн", "Маркетинг", "Компьютерн", "Технологии програм",
    "Теория информа", "практик", "FTD", "ФТД",
]


def read_passport(doc: Document) -> dict:
    result: dict = {}
    for table in doc.tables[:8]:
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            value = cells[-1] if len(cells) == 2 else " | ".join(cells[1:])
            if "дисциплин" in label or "практик" in label:
                result["discipline_raw"] = value
                m = re.search(r"(Б\d+\.[А-ЯA-Z]+\.\d+(?:\.\d+)?(?:\([А-ЯA-Z]+\))?)", value)
                if m:
                    result["discipline_code"] = m.group(1)
            elif "направлен" in label and "профил" not in label:
                result["direction_raw"] = value
                m = re.search(r"(\d{2}\.\d{2}\.\d{2})", value)
                if m:
                    result["direction_code"] = m.group(1)
            elif "профиль" in label or "направленност" in label:
                result["profile_name"] = value
            elif "кафедр" in label:
                result["department_name"] = value
    return result


def scan_plx(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    info: dict = {"file": path.name, "sheets": wb.sheetnames}

    ws = wb["Титул"]
    titul: list[str] = []
    for row in ws.iter_rows(max_row=50, values_only=True):
        for c in row:
            if c and str(c).strip():
                s = str(c).strip()
                if len(s) > 4 and s not in titul:
                    titul.append(s[:150])
    info["titul"] = titul

    ws = wb["План"]
    matches = []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        idx = str(row[1] or "").strip()
        name = str(row[2] or "").strip()
        rowtxt = " ".join(str(c) for c in row if c)
        if not idx and not name:
            continue
        if any(t.lower() in rowtxt.lower() for t in SEARCH_TERMS):
            matches.append(
                {
                    "row": i,
                    "index": idx,
                    "name": name,
                    "credits": row[9] or row[8],
                    "hours_total": row[11] or row[10],
                    "contact": row[12],
                    "aud": row[13],
                    "sr": row[14],
                    "exam": row[3],
                    "zach": row[4],
                    "kp": row[6],
                    "kr": row[7],
                }
            )
    info["plan_matches"] = matches

    comp_sheet = "Компетенции(2)"
    if comp_sheet in wb.sheetnames:
        ws = wb[comp_sheet]
        comp = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() if c else "" for c in row]
            code_cell = cells[2] if len(cells) > 2 else ""
            name_cell = cells[3] if len(cells) > 3 else ""
            comps = cells[5] if len(cells) > 5 else ""
            if re.match(r"Б\d+\.", code_cell):
                comp.append({"code": code_cell, "name": name_cell, "competencies": comps[:200]})
        info["competencies"] = [c for c in comp if any(
            k in c["name"] or k in c["code"] for k in ["01.07", "01.03", "02.05", "01.13", "03"]
        )][:15]

    wb.close()
    return info


def scan_docx(path: Path) -> dict:
    doc = Document(path)
    passport = read_passport(doc)
    styles: dict[str, int] = {}
    for p in doc.paragraphs:
        if p.text.strip() and p.style:
            styles[p.style.name] = styles.get(p.style.name, 0) + 1
    return {
        "file": path.name,
        "passport": passport,
        "tables_count": len(doc.tables),
        "top_styles": sorted(styles.items(), key=lambda x: -x[1])[:6],
    }


def main() -> None:
    data = {
        "plx": [scan_plx(SAMPLES / f) for f in PLX_FILES if (SAMPLES / f).exists()],
        "docx": [scan_docx(SAMPLES / f) for f in DOCX_FILES if (SAMPLES / f).exists()],
        "all_docx_in_samples": sorted(p.name for p in SAMPLES.glob("*.docx")),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written {OUT}")


if __name__ == "__main__":
    main()
