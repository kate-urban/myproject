#!/usr/bin/env python3
"""Аудит извлечения и внутренней сверки РПД по samples/ИЛИП."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.doc_converter import convert_doc_file_to_docx
from app.services.rpd_extractor import extract_rpd
from app.services.validation.rules import ValidationContext, DEFAULT_RULE_IDS
from app.models import PlanDiscipline
from app.services.validation.engine import _evaluate, _build_context


def _find_ilip_dir() -> Path | None:
    for path in ROOT.joinpath("samples").rglob("*05.03.06*"):
        if path.is_dir():
            return path
    return None


def _extract(path: Path):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        src = td_path / "s.doc"
        shutil.copy2(path, src)
        dst = td_path / "s.docx"
        convert_doc_file_to_docx(src, dst)
        return extract_rpd(dst.read_bytes(), path.name)


def _internal_rules(ctx: ValidationContext) -> list[dict]:
    internal = {"R012", "R013", "R014", "R015", "R016", "R017", "R018", "R019", "R025", "R026", "R027"}
    results = _evaluate(ctx, rule_ids=sorted(internal))
    return [
        {
            "rule": r.rule_id,
            "passed": r.passed,
            "skipped": r.skipped,
            "message": r.message[:100],
        }
        for r in results
        if not r.skipped and not r.passed
    ]


def main() -> int:
    ilip = _find_ilip_dir()
    if ilip is None:
        print("ILIP folder not found")
        return 1

    docs = sorted(ilip.glob("*.doc"))
    print(f"Auditing {len(docs)} documents in {ilip.name}\n")
    summary = []

    for doc in docs:
        try:
            rpd = _extract(doc)
            discipline = PlanDiscipline(
                code=rpd.discipline_code or "?",
                name=rpd.discipline_name or doc.stem,
                hours_total=rpd.hours_total,
                hours_contact=rpd.volume.contact,
                hours_sr=rpd.volume.sr,
                hours_control=rpd.volume.control,
                credits=rpd.credits,
            )
            plan = SimpleNamespace(
                form="ochnaya",
                profile=SimpleNamespace(
                    name="Природопользование",
                    direction=SimpleNamespace(code="05.03.06", name="Экология"),
                ),
            )
            ctx = _build_context(plan=plan, discipline=discipline, rpd=rpd)
            fails = _internal_rules(ctx)
            row = {
                "file": doc.name,
                "code": rpd.discipline_code,
                "zuv31": len(rpd.topics31_zuv_phrases),
                "matrix36": len(rpd.matrix_36_rows),
                "questions": len(rpd.sr_questions),
                "sr_rows": len(rpd.sr_rows),
                "fails": fails,
            }
            summary.append(row)
            status = "OK" if not fails else f"{len(fails)} issues"
            print(f"{doc.name[:40]:40} | {rpd.discipline_code or '?':12} | zuv={row['zuv31']:2} m36={row['matrix36']:2} | {status}")
        except Exception as exc:
            print(f"{doc.name[:40]:40} | ERROR: {exc}")

    out = ROOT / "docs" / "ilip_audit_report.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
