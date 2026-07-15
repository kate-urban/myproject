#!/usr/bin/env python3
"""Применить канонические {{TAG}} к tagged-макетам РПД и ФОС."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from docx import Document

from scripts.docgen.maket_layouts import (
    FOS_PASSPORT_LINES,
    FOS_TITLE_HEAD_CELL,
    RPD_COMPOSERS_BLOCK,
    RPD_PASSPORT_LINES,
    RPD_RESTORE_AFTER_SECTION_12,
    RPD_TITLE_DIRECTOR_CELL,
    RPD_TITLE_HEAD_CELL,
)

RPD_TAGGED = ROOT / "templates" / "tagged" / "Maket_RPd_FGOS_3_tagged.docx"
FOS_TAGGED = ROOT / "templates" / "tagged" / "Maket_FOSd_FGOS_3_tagged.docx"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _find_paragraph_index(doc: Document, predicate) -> int | None:
    for i, para in enumerate(doc.paragraphs):
        if predicate(para.text):
            return i
    return None


def _set_paragraph_text(para, text: str) -> None:
    para.text = text


def _replace_paragraph_range(doc: Document, start: int, lines: list[str]) -> None:
    """Заменить абзацы [start, start+len(lines)) содержимым lines."""
    for offset, line in enumerate(lines):
        idx = start + offset
        if idx >= len(doc.paragraphs):
            doc.add_paragraph(line)
        else:
            _set_paragraph_text(doc.paragraphs[idx], line)


def apply_rpd_title(doc: Document) -> None:
    if not doc.tables:
        raise ValueError("Нет таблиц")
    row = doc.tables[0].rows[0]
    row.cells[0].text = RPD_TITLE_DIRECTOR_CELL
    if len(row.cells) > 2:
        row.cells[2].text = RPD_TITLE_HEAD_CELL


def apply_fos_title(doc: Document) -> None:
    if not doc.tables:
        raise ValueError("Нет таблиц")
    row = doc.tables[0].rows[0]
    row.cells[0].text = ""
    if len(row.cells) > 2:
        row.cells[2].text = FOS_TITLE_HEAD_CELL


def _find_document_header_index(doc: Document, *, kind: str) -> int | None:
    for i, para in enumerate(doc.paragraphs):
        compact = _norm(para.text).replace(" ", "")
        if kind == "rpd" and "рабочая" in compact and "программа" in compact:
            return i
        if kind == "fos" and "фонд" in compact and "оценочн" in compact:
            return i
    return None


def _find_passport_index(doc: Document, *, kind: str) -> int | None:
    header_idx = _find_document_header_index(doc, kind=kind)
    if header_idx is None:
        return None
    for i in range(header_idx + 1, min(header_idx + 20, len(doc.paragraphs))):
        n = _norm(doc.paragraphs[i].text)
        if "дисциплин" in n:
            return i
    return None


def apply_passport(doc: Document, *, kind: str) -> None:
    lines = RPD_PASSPORT_LINES if kind == "rpd" else FOS_PASSPORT_LINES
    idx = _find_passport_index(doc, kind=kind)
    if idx is None:
        raise ValueError(f"Не найден блок паспорта ({kind})")
    _replace_paragraph_range(doc, idx, lines)


def fix_rpd_misplaced_passport(doc: Document) -> None:
    """Убрать ошибочный дубликат паспорта в разделе 1.2 («Место дисциплины»)."""
    passport_idx = _find_passport_index(doc, kind="rpd")
    if passport_idx is None:
        return
    for i in range(passport_idx + 1, len(doc.paragraphs)):
        text = doc.paragraphs[i].text
        if _norm(text).startswith("дисциплина:") and "{{" in text:
            _replace_paragraph_range(doc, i, RPD_RESTORE_AFTER_SECTION_12)
            return


def apply_composers(doc: Document) -> None:
    idx = _find_paragraph_index(doc, lambda t: _norm(t).startswith("составители"))
    if idx is None:
        idx = _find_paragraph_index(
            doc, lambda t: "составител" in _norm(t) and len(t.strip()) < 40
        )
    if idx is None:
        raise ValueError("Не найден блок «Составители»")
    _replace_paragraph_range(doc, idx, RPD_COMPOSERS_BLOCK)


def apply_rpd(doc: Document) -> None:
    apply_rpd_title(doc)
    apply_passport(doc, kind="rpd")
    fix_rpd_misplaced_passport(doc)
    apply_composers(doc)


def apply_fos(doc: Document) -> None:
    apply_fos_title(doc)
    apply_passport(doc, kind="fos")


def apply_file(path: Path, kind: str) -> None:
    doc = Document(str(path))
    if kind == "rpd":
        apply_rpd(doc)
    else:
        apply_fos(doc)
    doc.save(str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Канонические {{TAG}} в макетах РПД/ФОС")
    parser.add_argument(
        "--kind",
        choices=("rpd", "fos", "all"),
        default="all",
        help="Тип макета",
    )
    args = parser.parse_args(argv)

    targets: list[tuple[Path, str]] = []
    if args.kind in ("rpd", "all") and RPD_TAGGED.is_file():
        targets.append((RPD_TAGGED, "rpd"))
    if args.kind in ("fos", "all") and FOS_TAGGED.is_file():
        targets.append((FOS_TAGGED, "fos"))

    if not targets:
        print("Tagged-макеты не найдены в templates/tagged/", file=sys.stderr)
        return 1

    for path, kind in targets:
        try:
            apply_file(path, kind)
            print(f"OK  {path.name} ({kind})")
        except Exception as exc:
            print(f"ERR {path.name}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
