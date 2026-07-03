"""Подстановка разделов в макет Word по совпадению заголовков (без {{плейсхолдеров}})."""

from __future__ import annotations

import re

from docx import Document
from docx.text.paragraph import Paragraph

from app.utils.html_converter import insert_html_after_paragraph

_HEADING_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)[\.)]\s*")


def normalize_heading(text: str) -> str:
    cleaned = re.sub(r"[\t\r\n]+", " ", text.strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[,;:\.]+$", "", cleaned)
    return cleaned


def heading_level(text: str) -> int:
    match = _HEADING_NUMBER_RE.match(text.strip())
    if not match:
        return 99
    return match.group(1).count(".") + 1


def headings_match(section_name: str, heading_text: str) -> bool:
    left = normalize_heading(section_name)
    right = normalize_heading(heading_text)
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    left_no_num = _HEADING_NUMBER_RE.sub("", left).strip()
    right_no_num = _HEADING_NUMBER_RE.sub("", right).strip()
    if left_no_num and right_no_num:
        if left_no_num == right_no_num:
            return True
        if left_no_num in right_no_num or right_no_num in left_no_num:
            return True
    return False


def _is_heading_paragraph(paragraph: Paragraph) -> bool:
    text = paragraph.text.strip()
    if not text:
        return False
    style = (paragraph.style.name if paragraph.style else "").lower()
    if "heading" in style or "заголовок" in style:
        return True
    if "рпд пункт" in style or "рпд подпункт" in style:
        return True
    if "фосд" in style and "заголов" in style:
        return True
    return bool(_HEADING_NUMBER_RE.match(text))


def _collect_headings(doc: Document) -> list[tuple[int, str, int]]:
    headings: list[tuple[int, str, int]] = []
    for index, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()
        if not text or not _is_heading_paragraph(paragraph):
            continue
        headings.append((index, text, heading_level(text)))
    return headings


def inject_sections_by_headings(doc: Document, sections_data: dict[str, str]) -> int:
    """Вставляет HTML-содержимое разделов под подходящими заголовками макета."""
    injected = 0

    for section_name, html_content in sections_data.items():
        if not html_content or not str(html_content).strip():
            continue

        headings = _collect_headings(doc)
        if not headings:
            break

        match_pos = None
        for pos, (_, heading_text, _) in enumerate(headings):
            if headings_match(section_name, heading_text):
                match_pos = pos
                break
        if match_pos is None:
            continue

        anchor_index, _, level = headings[match_pos]
        end_index = len(doc.paragraphs)
        for next_index, _, next_level in headings[match_pos + 1 :]:
            if next_level <= level:
                end_index = next_index
                break

        content_start = anchor_index + 1
        if content_start >= end_index:
            anchor = doc.paragraphs[anchor_index]
            insert_html_after_paragraph(doc, anchor, html_content)
        else:
            first = doc.paragraphs[content_start]
            insert_html_after_paragraph(doc, first, html_content, replace_anchor=True)
            for idx in range(content_start + 1, end_index):
                doc.paragraphs[idx].clear()

        injected += 1

    return injected
