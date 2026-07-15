#!/usr/bin/env python3
"""Editable DOCX с {{TAG}}: выгрузка для правки и активация для экспорта."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from docx import Document
from docx.shared import Pt

EDITABLE_DIR = ROOT / "templates" / "editable"

RPD_SOURCE = ROOT / "templates" / "tagged" / "Maket_RPd_FGOS_3_tagged.docx"
FOS_SOURCE = ROOT / "templates" / "tagged" / "Maket_FOSd_FGOS_3_tagged.docx"

RPD_EDITABLE = EDITABLE_DIR / "РПД_FGOS3_макет_с_тегами.docx"
FOS_EDITABLE = EDITABLE_DIR / "ФОС_FGOS3_макет_с_тегами.docx"
GUIDE_DOCX = EDITABLE_DIR / "Справочник_тегов_РПД_ФОС.docx"

RPD_USER_EDIT = ROOT / "templates" / "tagged" / "РПД_FGOS3_макет_с_тегами.docx"
FOS_USER_EDIT = ROOT / "templates" / "tagged" / "ФОС_FGOS3_макет_с_тегами.docx"

LAYOUT_RPD = ROOT / "Layout" / "Maket_RPd_FGOS_3.docx"
LAYOUT_FOS = ROOT / "Layout" / "Maket_FOSd_FGOS_3.docx"
ACTIVE_RPD = ROOT / "templates" / "layout_Maket_RPd_FGOS_3.docx"
ACTIVE_FOS = ROOT / "templates" / "layout_Maket_FOSd_FGOS_3.docx"

RPD_USER_CANDIDATES = (RPD_USER_EDIT, RPD_EDITABLE, RPD_SOURCE)
FOS_USER_CANDIDATES = (FOS_USER_EDIT, FOS_EDITABLE, FOS_SOURCE)

_TAG_RE = re.compile(r"\{\{([^#%}][^}]*)\}\}")

TAG_HELP: dict[str, str] = {
    "DIRECTOR_LINE": "Должность и институт (слева «Согласовано»)",
    "DIRECTOR_NAME": "Расшифровка подписи директора института",
    "SIGNATURE_DIRECTOR": "PNG-подпись директора (отдельная строка над линией)",
    "HEAD_LINE": "Должность руководителя ОПОП",
    "HEAD_NAME": "Расшифровка подписи руководителя ОПОП",
    "SIGNATURE_HEAD": "PNG-подпись руководителя ОПОП",
    "APPROVAL_DATE": "Год / дата утверждения",
    "DISCIPLINE_CODE": "Шифр дисциплины по учебному плану (напр. Б1.О.13)",
    "DISCIPLINE_NAME": "Наименование дисциплины",
    "EDUCATION_LEVEL": "Уровень образования (бакалавriат / магистратура …)",
    "DIRECTION_CODE": "Код направления подготовки",
    "DIRECTION_NAME": "Наименование направления подготовки",
    "PROFILE_SPECIALIZATION": "Профиль (бак.) / магистерская программа / направленность",
    "DEPARTMENT_NAME": "Наименование кафедры",
    "AUTHOR1_DEGREE": "Учёное звание 1-го составителя",
    "AUTHOR1_POSITION": "Должность 1-го составителя",
    "AUTHOR1_NAME": "Ф.И.О. 1-го составителя полностью",
    "DEPT_PROTOCOL_NO": "№ протокола заседания кафедры",
    "DEPT_PROTOCOL_DAY": "День протокола",
    "DEPT_PROTOCOL_MONTH": "Месяц протокола",
    "DEPT_PROTOCOL_YEAR": "Год протокола",
    "DEPT_HEAD_DEGREE_NAME": "Звание и Ф.И.О. заведующего кафедрой",
    "SIGNATURE_DEPT_HEAD": "PNG-подпись заведующего кафедрой",
    "REAPPROVAL_ROWS": "Строки листа переутверждения",
    "DEPT_HEAD_LINE": "Устар.: не использовать в титуле РПД",
    "DEPT_HEAD_NAME": "Устар.: не использовать в титуле РПД",
}


def _scan_tags(path: Path) -> set[str]:
    found: set[str] = set()
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            for raw in _TAG_RE.findall(text):
                tag = raw.strip().replace("-", "_")
                if tag and " " not in tag:
                    found.add(tag)
    return found


def _apply_layout() -> None:
    script = ROOT / "scripts" / "docgen" / "apply_maket_layout.py"
    subprocess.run([sys.executable, str(script)], check=True, cwd=ROOT)


def _copy_templates() -> None:
    EDITABLE_DIR.mkdir(parents=True, exist_ok=True)
    if not RPD_SOURCE.is_file():
        raise FileNotFoundError(f"Нет {RPD_SOURCE}")
    if not FOS_SOURCE.is_file():
        raise FileNotFoundError(f"Нет {FOS_SOURCE}")
    shutil.copy2(RPD_SOURCE, RPD_EDITABLE)
    shutil.copy2(FOS_SOURCE, FOS_EDITABLE)


def _build_guide(*, rpd_tags: set[str], fos_tags: set[str]) -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    doc.add_heading("Справочник тегов {{TAG}} для макетов РПД и ФОС", level=0)
    doc.add_paragraph(
        "В папке templates/editable лежат два файла Word с уже расставленными тегами. "
        "Откройте их в Microsoft Word, подправьте расположение текста и таблиц, "
        "но не меняйте имена тегов внутри двойных фигурных скобок."
    )

    doc.add_heading("Правила правки в Word", level=1)
    for line in (
        "Тег пишется строго так: {{ИМЯ_ТЕГА}} — латиница, цифры и подчёркивание.",
        "Не разрывайте {{ТЕГ}} на части разным форматированием (жирный/курсив посередине).",
        "В имени тега не используйте дефис «-» — только подчёркивание «_».",
        "SIGNATURE_* — отдельная строка/ячейка только для PNG-подписи.",
        "SECTION_* — содержимое разделов программы; расположение можно менять, имя — нет.",
        "После правки: activate_template.bat или python scripts/docgen/prepare_editable_templates.py --activate",
    ):
        doc.add_paragraph(line, style="List Bullet")

    doc.add_heading("Файлы для правки", level=1)
    table = doc.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    rows = [
        ("РПД_FGOS3_макет_с_тегами.docx", "Рабочая программа дисциплины"),
        ("ФОС_FGOS3_макет_с_тегами.docx", "Фонд оценочных средств"),
    ]
    table.rows[0].cells[0].text = "Файл"
    table.rows[0].cells[1].text = "Назначение"
    for index, (fname, purpose) in enumerate(rows, start=1):
        table.rows[index].cells[0].text = fname
        table.rows[index].cells[1].text = purpose

    def _add_tag_table(title: str, tags: set[str]) -> None:
        doc.add_heading(title, level=1)
        header_tags = sorted(t for t in tags if not t.startswith("SECTION_"))
        section_tags = sorted(t for t in tags if t.startswith("SECTION_"))
        tbl = doc.add_table(rows=len(header_tags) + 1, cols=3)
        tbl.style = "Table Grid"
        hdr = tbl.rows[0].cells
        hdr[0].text = "Тег"
        hdr[1].text = "Где в макете"
        hdr[2].text = "Пример значения"
        examples = {
            "DISCIPLINE_CODE": "Б1.О.13",
            "DISCIPLINE_NAME": "Технологии программирования",
            "DIRECTION_CODE": "09.03.02",
            "DIRECTION_NAME": "Информационные системы и технологии",
            "EDUCATION_LEVEL": "уровень бакалавriата",
            "PROFILE_SPECIALIZATION": "Робототехнические системы…",
            "DEPARTMENT_NAME": "информационных систем и технологий",
            "APPROVAL_DATE": "2021",
        }
        for row_index, tag in enumerate(header_tags, start=1):
            cells = tbl.rows[row_index].cells
            cells[0].text = f"{{{{{tag}}}}}"
            cells[1].text = TAG_HELP.get(tag, "—")
            cells[2].text = examples.get(tag, "")
        doc.add_paragraph(f"Тегов SECTION_* (тело программы): {len(section_tags)} шт.")

    _add_tag_table("Теги макета РПД", rpd_tags)
    _add_tag_table("Теги макета ФОС", fos_tags)

    doc.add_heading("Расположение блоков РПД", level=1)
    for line in (
        "Титул, таблица 1: слева «Согласовано» — DIRECTOR_*, справа «Утверждаю» — HEAD_*.",
        "После «Р А Б О Ч А Я   П Р О Г Р А М М А» — паспорт: дисциплина, уровень, направление, профиль, кафедра.",
        "Блок «Составители» — авторы, протокол кафедры, SIGNATURE_DEPT_HEAD.",
        "Дальше SECTION_* — разделы 1–7 программы.",
    ):
        doc.add_paragraph(line, style="List Bullet")

    doc.add_heading("Расположение блоков ФОС", level=1)
    for line in (
        "Титул: только справа «Утверждено» — HEAD_*; левая ячейка пустая.",
        "После «Ф О Н Д   О Ц Е Н О Ч Н Ы Х…» — тот же паспорт, что у РПД (с «дисциплины (модуля)»).",
    ):
        doc.add_paragraph(line, style="List Bullet")

    doc.save(GUIDE_DOCX)


def _pick_source(candidates: tuple[Path, ...]) -> Path | None:
    for path in candidates:
        if path.is_file() and not path.name.startswith("~$"):
            return path
    return None


def _copy_with_fallback(source: Path, dest: Path, *, kind: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, dest)
    except PermissionError:
        print(
            f"WARN {kind}: не удалось записать {dest.name} — закройте файл в Word",
            file=sys.stderr,
        )


def _activate_one(
    *,
    kind: str,
    candidates: tuple[Path, ...],
    layout_dest: Path,
    tagged_dest: Path,
    active_dest: Path,
) -> Path | None:
    source = _pick_source(candidates)
    if source is None:
        print(f"SKIP {kind}: нет файла для активации", file=sys.stderr)
        return None

    _copy_with_fallback(source, layout_dest, kind=kind)
    _copy_with_fallback(source, active_dest, kind=kind)
    _copy_with_fallback(source, tagged_dest, kind=kind)

    print(f"OK  {kind} <- {source.name}")
    print(f"    -> {layout_dest.relative_to(ROOT)}")
    print(f"    -> {active_dest.relative_to(ROOT)}")
    print(f"    -> {tagged_dest.relative_to(ROOT)}")
    return source


def activate_templates(*, rpd: bool = True, fos: bool = False) -> None:
    """Подключить правки к экспорту на вкладке «Сверка»."""
    if rpd:
        _activate_one(
            kind="РПД",
            candidates=RPD_USER_CANDIDATES,
            layout_dest=LAYOUT_RPD,
            tagged_dest=RPD_SOURCE,
            active_dest=ACTIVE_RPD,
        )
    if fos:
        _activate_one(
            kind="ФОС",
            candidates=FOS_USER_CANDIDATES,
            layout_dest=LAYOUT_FOS,
            tagged_dest=FOS_SOURCE,
            active_dest=ACTIVE_FOS,
        )


def _import_back() -> None:
    """Скопировать правки из templates/editable/ в templates/tagged/."""
    tagged = ROOT / "templates" / "tagged"
    tagged.mkdir(parents=True, exist_ok=True)
    if RPD_EDITABLE.is_file():
        shutil.copy2(RPD_EDITABLE, RPD_SOURCE)
    if FOS_EDITABLE.is_file():
        shutil.copy2(FOS_EDITABLE, FOS_SOURCE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Editable DOCX с {{TAG}} для ручной правки")
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Забрать правки из templates/editable/ в templates/tagged/",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Применить правки к экспорту (Layout/ + templates/layout_*.docx)",
    )
    parser.add_argument(
        "--activate-fos",
        action="store_true",
        help="Вместе с --activate: также обновить макет ФОС",
    )
    parser.add_argument(
        "--skip-layout",
        action="store_true",
        help="Не запускать apply_maket_layout.py",
    )
    args = parser.parse_args(argv)

    if args.activate:
        activate_templates(rpd=True, fos=args.activate_fos)
        print(
            "Готово. Перезапуск сервера не обязателен — "
            "экспорт использует templates/layout_*.docx"
        )
        return 0

    if args.do_import:
        _import_back()
        print(f"OK  import -> {RPD_SOURCE.name}, {FOS_SOURCE.name}")
        return 0

    if not args.skip_layout:
        _apply_layout()
    _copy_templates()
    _build_guide(rpd_tags=_scan_tags(RPD_EDITABLE), fos_tags=_scan_tags(FOS_EDITABLE))

    print(f"OK  {RPD_EDITABLE}")
    print(f"OK  {FOS_EDITABLE}")
    print(f"OK  {GUIDE_DOCX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
