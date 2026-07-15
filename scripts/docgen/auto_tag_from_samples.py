#!/usr/bin/env python3
"""
Анализ эталонов samples/Информационные материалы и расстановка {{TAG}} в Word.

Не генерирует текст документа — только создаёт шаблоны в templates/tagged/.

Использование:
  python scripts/docgen/auto_tag_from_samples.py
  python scripts/docgen/auto_tag_from_samples.py --input path/to/file.htm --out templates/tagged
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from docx import Document
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLES = ROOT / "samples" / "Информационные материалы"
RULES_PATH = Path(__file__).with_name("tagging_rules.yaml")
DEFAULT_OUT = ROOT / "templates" / "tagged"

_DISC_CODE_RE = re.compile(
    r"^(Б\d\.[ОВ]\.\d{2}(?:\.\d{2})?)(?:\s+(.*))?$", re.IGNORECASE
)
_DIR_CODE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{2})(?:\s+(.*))?$")
_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*[.)]\s+.+")
_UNDERSCORE_NAME_RE = re.compile(
    r"_{3,}\s*/\s*([А-ЯЁA-Z][а-яёa-z\.\s\-]+)\s*/", re.UNICODE
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned[:80] or "section"


def _load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def _convert_to_docx(source: Path, tmp_dir: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix == ".docx":
        target = tmp_dir / source.name
        shutil.copy2(source, target)
        return target
    if suffix in {".htm", ".html", ".doc"}:
        import os
        import subprocess

        soffice = None
        env = os.getenv("LIBREOFFICE_PATH", "").strip()
        if env and Path(env).is_file():
            soffice = Path(env)
        if soffice is None:
            for base in (
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            ):
                candidate = Path(base) / "LibreOffice" / "program" / "soffice.exe"
                if candidate.is_file():
                    soffice = candidate
                    break
        if soffice is None:
            found = shutil.which("soffice")
            soffice = Path(found) if found else None
        if soffice is None:
            raise RuntimeError(
                f"Для {source.name} нужен LibreOffice (--convert-to docx)"
            )
        cmd = [
            str(soffice),
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(tmp_dir),
            str(source.resolve()),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "LibreOffice error").strip())
        converted = tmp_dir / f"{source.stem}.docx"
        if not converted.is_file():
            raise RuntimeError("LibreOffice не создал .docx")
        return converted
    raise ValueError(f"Формат не поддерживается для разметки: {suffix}")


def _paragraphs(doc: Document) -> list[Paragraph]:
    items: list[Paragraph] = []
    for p in doc.paragraphs:
        items.append(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    items.append(p)
    return items


def _match_any(text: str, patterns: list[str]) -> bool:
    low = _norm(text)
    return any(p.lower() in low for p in patterns)


def _replace_discipline_code(text: str) -> str | None:
    m = _DISC_CODE_RE.match(text.strip())
    if not m:
        return None
    return "{{DISCIPLINE_CODE}}" + (f" {m.group(2).strip()}" if m.group(2) else "")


def _replace_direction_code(text: str) -> str | None:
    m = _DIR_CODE_RE.match(text.strip())
    if not m:
        return None
    return "{{DIRECTION_CODE}}" + (f" {m.group(2).strip()}" if m.group(2) else "")


def _apply_text_rules(paragraph: Paragraph, stats: dict) -> None:
    text = paragraph.text.strip()
    if not text or "{{" in text:
        return
    low = _norm(text)

    if "утверждаю" in low and "директор" in low:
        paragraph.text = "{{DIRECTOR_LINE}}"
        stats["DIRECTOR_LINE"] = stats.get("DIRECTOR_LINE", 0) + 1
        return

    if "руководитель образовательной программы" in low or "руководитель опоп" in low:
        paragraph.text = "{{HEAD_LINE}}"
        stats["HEAD_LINE"] = stats.get("HEAD_LINE", 0) + 1
        return

    if low.startswith("дисциплина:") or (low.startswith("дисциплина") and "___" in text):
        paragraph.text = "Дисциплина: {{DISCIPLINE_CODE}} {{DISCIPLINE_NAME}}"
        stats["DISCIPLINE_NAME"] = stats.get("DISCIPLINE_NAME", 0) + 1
        stats["DISCIPLINE_CODE"] = stats.get("DISCIPLINE_CODE", 0) + 1
        return

    if "протокол изменений" in low or "переутвержден" in low:
        paragraph.text = "{{REAPPROVAL_ROWS}}"
        stats["REAPPROVAL_ROWS"] = stats.get("REAPPROVAL_ROWS", 0) + 1
        return

    replaced = _replace_discipline_code(text)
    if replaced and replaced != text:
        paragraph.text = replaced
        stats["DISCIPLINE_CODE"] = stats.get("DISCIPLINE_CODE", 0) + 1
        return

    replaced = _replace_direction_code(text)
    if replaced and replaced != text:
        paragraph.text = replaced
        stats["DIRECTION_CODE"] = stats.get("DIRECTION_CODE", 0) + 1
        return

    if _UNDERSCORE_NAME_RE.search(text) and len(text) < 120:
        # Строка «________ / ФИО /» — оставляем структуру, ФИО → тег расшифровки
        if "утверждаю" in low or stats.get("_last_block") == "director":
            paragraph.text = _UNDERSCORE_NAME_RE.sub(
                r"_________________/ {{DIRECTOR_NAME}} /", text
            )
            stats["DIRECTOR_NAME"] = stats.get("DIRECTOR_NAME", 0) + 1
            return
        if stats.get("_last_block") == "head":
            paragraph.text = _UNDERSCORE_NAME_RE.sub(
                r"_________________/ {{HEAD_NAME}} /", text
            )
            stats["HEAD_NAME"] = stats.get("HEAD_NAME", 0) + 1
            return


def _tag_signature_block(text: str, *, role: str) -> tuple[str, dict[str, int]]:
    """Титульная таблица: фиксированная структура с {{TAG}}."""
    stats: dict[str, int] = {}
    if "{{" in text:
        return text, stats

    sign_tag = {
        "director": "SIGNATURE_DIRECTOR",
        "head": "SIGNATURE_HEAD",
        "dept": "SIGNATURE_DEPT_HEAD",
    }[role]
    name_tag = {
        "director": "DIRECTOR_NAME",
        "head": "HEAD_NAME",
        "dept": "DEPT_HEAD_NAME",
    }[role]
    line_tag = {
        "director": "DIRECTOR_LINE",
        "head": "HEAD_LINE",
        "dept": "DEPT_HEAD_LINE",
    }[role]

    title_word = {
        "director": "Согласовано",
        "head": "Утверждаю",
        "dept": "Согласовано",
    }[role]
    prefix = [title_word, f"{{{{{line_tag}}}}}"]
    stats[line_tag] = 1
    stats[sign_tag] = 1
    stats[name_tag] = 1
    stats["APPROVAL_DATE"] = 1

    body = [
        f"{{{{{sign_tag}}}}}",
        "(подпись)",
        f"_________________/ {{{{{name_tag}}}}} /",
        "«___» ______________ {{APPROVAL_DATE}}",
    ]
    return "\n".join(prefix + body), stats


def _apply_rpd_title_table(doc: Document, stats: dict) -> bool:
    """Первая таблица РПД: слева «Согласовано» (директор), справа «Утверждаю» (ОПОП)."""
    if not doc.tables:
        return False
    table = doc.tables[0]
    if not table.rows:
        return False
    row = table.rows[0]
    if len(row.cells) < 3:
        return False
    left = _norm(row.cells[0].text)
    right = _norm(row.cells[2].text)
    # РПД: слева «Согласовано» (директор), справа «Утверждаю» (ОПОП)
    from scripts.docgen.maket_layouts import RPD_TITLE_DIRECTOR_CELL, RPD_TITLE_HEAD_CELL

    row.cells[0].text = RPD_TITLE_DIRECTOR_CELL
    row.cells[2].text = RPD_TITLE_HEAD_CELL
    stats["DIRECTOR_LINE"] = stats.get("DIRECTOR_LINE", 0) + 1
    stats["SIGNATURE_DIRECTOR"] = stats.get("SIGNATURE_DIRECTOR", 0) + 1
    stats["DIRECTOR_NAME"] = stats.get("DIRECTOR_NAME", 0) + 1
    stats["HEAD_LINE"] = stats.get("HEAD_LINE", 0) + 1
    stats["SIGNATURE_HEAD"] = stats.get("SIGNATURE_HEAD", 0) + 1
    stats["HEAD_NAME"] = stats.get("HEAD_NAME", 0) + 1
    stats["APPROVAL_DATE"] = stats.get("APPROVAL_DATE", 0) + 2
    return True


def _apply_fos_title_table(doc: Document, stats: dict) -> bool:
    if not doc.tables:
        return False
    table = doc.tables[0]
    if not table.rows or len(table.rows[0].cells) < 3:
        return False
    from scripts.docgen.maket_layouts import FOS_TITLE_HEAD_CELL

    row = table.rows[0]
    row.cells[0].text = ""
    row.cells[2].text = FOS_TITLE_HEAD_CELL
    stats["HEAD_LINE"] = stats.get("HEAD_LINE", 0) + 1
    stats["SIGNATURE_HEAD"] = stats.get("SIGNATURE_HEAD", 0) + 1
    stats["HEAD_NAME"] = stats.get("HEAD_NAME", 0) + 1
    stats["APPROVAL_DATE"] = stats.get("APPROVAL_DATE", 0) + 1
    return True


def _is_fos_document(doc: Document, source_hint: str = "") -> bool:
    if "fos" in source_hint.lower():
        return True
    for para in doc.paragraphs[:30]:
        if "фонд оценочных" in _norm(para.text):
            return True
    return False


def _apply_title_tables(doc: Document, stats: dict, *, source_hint: str = "") -> bool:
    if _is_fos_document(doc, source_hint):
        return _apply_fos_title_table(doc, stats)
    return _apply_rpd_title_table(doc, stats)


def _apply_table_cell_rules(doc: Document, stats: dict, *, source_hint: str = "") -> None:
    if _apply_title_tables(doc, stats, source_hint=source_hint):
        return
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if not text or "{{" in text:
                    continue
                low = _norm(text)

                if ("директор института" in low or "утверждаю" in low) and "руководитель образовательной" not in low:
                    tagged, partial = _tag_signature_block(text, role="director")
                    cell.text = tagged
                    for k, v in partial.items():
                        stats[k] = stats.get(k, 0) + v
                    continue

                if "руководитель образовательной программы" in low or "руководитель опоп" in low or (
                    low.startswith("согласовано") and "утверждаю" not in low
                ):
                    tagged, partial = _tag_signature_block(text, role="head")
                    cell.text = tagged
                    for k, v in partial.items():
                        stats[k] = stats.get(k, 0) + v
                    continue

                if "заведующий кафедрой" in low:
                    tagged, partial = _tag_signature_block(text, role="dept")
                    cell.text = tagged
                    for k, v in partial.items():
                        stats[k] = stats.get(k, 0) + v
                    continue

                m = _DISC_CODE_RE.search(text)
                if m:
                    name = (m.group(2) or "").strip()
                    cell.text = "{{DISCIPLINE_CODE}}" + (f" {name}" if name else "")
                    if name:
                        cell.text = f"{{{{DISCIPLINE_CODE}}}} {{{{DISCIPLINE_NAME}}}}"
                    stats["DISCIPLINE_CODE"] = stats.get("DISCIPLINE_CODE", 0) + 1
                    if name:
                        stats["DISCIPLINE_NAME"] = stats.get("DISCIPLINE_NAME", 0) + 1
                    continue

                m = _DIR_CODE_RE.search(text)
                if m:
                    name = (m.group(2) or "").strip()
                    cell.text = "{{DIRECTION_CODE}}" + (f" {{{{DIRECTION_NAME}}}}" if name else "")
                    stats["DIRECTION_CODE"] = stats.get("DIRECTION_CODE", 0) + 1
                    if name:
                        stats["DIRECTION_NAME"] = stats.get("DIRECTION_NAME", 0) + 1
                    continue

                if low.startswith("дисциплина:"):
                    cell.text = "Дисциплина: {{DISCIPLINE_CODE}} {{DISCIPLINE_NAME}}"
                    stats["DISCIPLINE_CODE"] = stats.get("DISCIPLINE_CODE", 0) + 1
                    stats["DISCIPLINE_NAME"] = stats.get("DISCIPLINE_NAME", 0) + 1


def _insert_signature_before(
    para: Paragraph,
    tag: str,
    stats: dict,
) -> None:
    if tag in (para.text or ""):
        return
    prev = para._element.getprevious()
    if prev is not None:
        prev_text = Paragraph(prev, para._parent).text or ""
        if tag in prev_text:
            return
    try:
        para.insert_paragraph_before(f"{{{{{tag}}}}}")
    except (AttributeError, TypeError):
        return
    stats[tag] = stats.get(tag, 0) + 1


def _apply_signature_rules(paragraphs: list[Paragraph], stats: dict) -> None:
    for i, para in enumerate(paragraphs):
        text = _norm(para.text)
        if "(подпись)" not in text:
            continue
        context = " ".join(_norm(paragraphs[j].text) for j in range(max(0, i - 8), i))
        if "утверждаю" in context or "директор института" in context:
            _insert_signature_before(para, "SIGNATURE_DIRECTOR", stats)
        elif (
            "руководитель образовательной программы" in context
            or "руководитель опоп" in context
            or "согласовано" in context
        ):
            _insert_signature_before(para, "SIGNATURE_HEAD", stats)
        elif "заведующий кафедрой" in context:
            _insert_signature_before(para, "SIGNATURE_DEPT_HEAD", stats)


def _apply_section_placeholders(doc: Document, stats: dict) -> None:
    """После заголовка раздела — {{SECTION_<slug>}} если тело не пустое."""
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text or "{{" in text:
            continue
        if not _HEADING_RE.match(text):
            continue
        low = _norm(text)
        if any(x in low for x in ("паспорт", "титул", "содержание")):
            continue
        if i + 1 >= len(doc.paragraphs):
            continue
        nxt = doc.paragraphs[i + 1]
        slug = _slug(text)
        placeholder = f"{{{{SECTION_{slug}}}}}"
        if placeholder in nxt.text:
            continue
        if not nxt.text.strip():
            nxt.text = placeholder
        else:
            # Вставить новый абзац между заголовком и телом
            nxt.insert_paragraph_before(placeholder)
        stats[f"SECTION_{slug}"] = stats.get(f"SECTION_{slug}", 0) + 1


def tag_docx(docx_path: Path, stats: dict | None = None) -> Document:
    stats = stats if stats is not None else {}
    doc = Document(str(docx_path))
    paragraphs = _paragraphs(doc)

    block = ""
    for para in paragraphs:
        low = _norm(para.text)
        if "утверждаю" in low:
            block = "director"
        elif "руководитель образовательной" in low or "согласовано" in low:
            block = "head"
        stats["_last_block"] = block
        _apply_text_rules(para, stats)

    _apply_table_cell_rules(doc, stats, source_hint=docx_path.stem)

    paragraphs = _paragraphs(doc)
    _apply_signature_rules(paragraphs, stats)
    _apply_section_placeholders(doc, stats)
    stats.pop("_last_block", None)
    return doc


def _discover_sources(folder: Path) -> list[Path]:
    patterns = ("*.docx", "*.doc", "*.htm", "*.html")
    files: list[Path] = []
    for pat in patterns:
        files.extend(folder.glob(pat))
    return sorted(set(files))


def process_file(source: Path, out_dir: Path) -> tuple[Path, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stats: dict = {"source": source.name}
    with tempfile.TemporaryDirectory() as tmp:
        docx = _convert_to_docx(source, Path(tmp))
        doc = tag_docx(docx, stats)
        out_name = f"{source.stem}_tagged.docx"
        out_path = out_dir / out_name
        if out_path.exists():
            out_path.unlink()
        doc.save(str(out_path))
    return out_path, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Авто-разметка {{TAG}} по эталонам")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_SAMPLES,
        help="Файл или папка с эталонами",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        default=DEFAULT_OUT,
        help="Каталог для tagged.docx",
    )
    args = parser.parse_args(argv)

    sources: list[Path]
    if args.input.is_file():
        sources = [args.input]
    elif args.input.is_dir():
        sources = _discover_sources(args.input)
    else:
        print(f"Не найдено: {args.input}", file=sys.stderr)
        return 1

    if not sources:
        print(f"Нет .docx/.htm в {args.input}", file=sys.stderr)
        return 1

    manifest: list[dict] = []
    for src in sources:
        try:
            out_path, stats = process_file(src, args.out)
            try:
                rel_out = out_path.relative_to(ROOT)
            except ValueError:
                rel_out = out_path
            manifest.append({"source": src.name, "output": str(rel_out), **stats})
            print(f"OK  {src.name} -> {out_path}")
        except Exception as exc:
            print(f"SKIP {src.name}: {exc}", file=sys.stderr)
            manifest.append({"source": src.name, "error": str(exc)})

    manifest_path = args.out / "tagging_manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
