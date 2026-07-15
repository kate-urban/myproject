"""Разбивает inline-скрипт validation.html на модули static/js/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Восстановить inline-скрипт из модулей нельзя — читаем из _extracted_script если есть
extracted = ROOT / "_extracted_script.js"
if extracted.is_file():
    lines = extracted.read_text(encoding="utf-8").splitlines(keepends=True)
else:
    html = (ROOT / "validation.html").read_text(encoding="utf-8")
    if "<script>\n" not in html:
        raise SystemExit("validation.html already split; use _extracted_script.js backup")
    start = html.index("<script>\n") + len("<script>\n")
    end = html.index("\n  </script>", start)
    lines = html[start:end].splitlines(keepends=True)


def find_line(prefix: str) -> int:
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            return index
    raise SystemExit(f"marker not found: {prefix!r}")


i_rules_start = find_line("    /** Подсказки:")
i_toast = find_line("    function toast(")
i_section_match = find_line("    function sectionMatchesRule(")
i_ensure_doc = find_line("    function ensureDocHtml(")
i_run_val = find_line("    async function runValidation(")
i_doc_save_bind = find_line('    document.getElementById("docEditorSave").onclick')

rules_block = lines[i_rules_start:i_toast] + lines[i_section_match:i_ensure_doc]
editor_block = lines[i_ensure_doc:i_run_val] + lines[i_doc_save_bind:]
page_block = lines[:i_rules_start] + lines[i_toast:i_section_match] + lines[i_run_val:i_doc_save_bind]

rules_header = "/** Метаданные правил сверки R/F и форматирование ошибок. */\n"
editor_header = "/** Встроенный редактор РПД/ФОС на странице сверки. */\n"
page_header = "/** Основная логика страницы /validation. */\n"

js_dir = ROOT / "static" / "js"
(js_dir / "validation_rules.js").write_text(rules_header + "".join(rules_block), encoding="utf-8")
(js_dir / "validation_editor.js").write_text(editor_header + "".join(editor_block), encoding="utf-8")
(js_dir / "validation_page.js").write_text(page_header + "".join(page_block), encoding="utf-8")
print("OK: split complete")
