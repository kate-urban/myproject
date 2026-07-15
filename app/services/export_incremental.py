"""Фильтрация разделов для инкрементального экспорта в исходный DOCX."""

from __future__ import annotations

from pathlib import Path

from app.services.parser import DocumentParser


def original_section_content(source_path: str | Path) -> dict[str, str]:
    data = Path(source_path).read_bytes()
    _, sections = DocumentParser().parse_docx_sync(data)
    return {s.section_name: s.content or "" for s in sections}


def changed_sections_for_export(
    source_path: str | Path,
    sections_data: dict[str, str],
) -> dict[str, str]:
    """Только разделы, чьё HTML-содержимое отличается от исходного файла."""
    try:
        baseline = original_section_content(source_path)
    except Exception:
        return {
            name: content
            for name, content in sections_data.items()
            if content and str(content).strip()
        }

    changed: dict[str, str] = {}
    for name, content in sections_data.items():
        if not content or not str(content).strip():
            continue
        if baseline.get(name, "") != content:
            changed[name] = content
    return changed
