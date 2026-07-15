import asyncio
import io
import re
from dataclasses import dataclass
from html import escape
from typing import Dict, List, Optional

import fitz
from docx import Document as DocxDocument
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

# Стили Word → уровень в оглавлении (1=глава, 2=подглава)
HEADING_STYLE_LEVELS = {
    "рпд пункты": 1,
    "рпд подпункты": 2,
    "аннотация заголовок": 1,
    "аннотация подзаголовки": 2,
    "фосд заголовки": 1,
    "фосд позаголовки": 2,
}

SUBSUB_PATTERN = re.compile(r"^\d+\.\d+\.\d+[\.\)]?\s*\S")
CHAPTER_PATTERN = re.compile(r"^\d+[\.\)]\s*\S")
# Нумерованные вопросы ФОС/экзамена («2. Объясните…») — не заголовки разделов РПД
EXAM_QUESTION_HEADING_RE = re.compile(
    r"^\d+[\.\)]\s+(?:"
    r"объясните|перечислите|опишите|раскройте|сформулируйте|назовите|"
    r"дайте|приведите|сравните|определите|решите|вычислите|постройте|"
    r"найдите|докажите|разработайте|составьте|проанализируйте|"
    r"охарактеризуйте|укажите|рассмотрите|оцените|выберите|"
    r"какие|каков|что\s+такое|в\s+ч[её]м|почему|как\s+"
    r")\b",
    re.IGNORECASE,
)
MAJOR_SECTION_KEYWORDS = (
    "перечень",
    "планируем",
    "компетенц",
    "содержание",
    "фонд",
    "объем",
    "объём",
    "контроль",
    "литератур",
    "ресурс",
    "условия",
    "организац",
    "универсальн",
    "общепроф",
    "профессиональн",
    "индикатор",
    "результат",
)


@dataclass
class ParsedSection:
    section_name: str
    content: str
    level: int
    order_index: int = 0
    parent_index: Optional[int] = None


class DocumentParser:
    """Парсер документов: приоритет — стили Word (РП/ФОС), иначе эвристики."""

    FALLBACK_SECTIONS = [
        "Введение",
        "Общие положения",
        "Основная часть",
        "Заключение",
        "Список литературы",
        "Приложения",
    ]

    def __init__(self, custom_sections: Optional[List[str]] = None):
        self.custom_sections = custom_sections

    @staticmethod
    def _style_name(para) -> str:
        """Имя стиля абзаца; в старых .doc после конвертации name иногда None."""
        if not para.style:
            return ""
        return para.style.name or ""

    @staticmethod
    def _font_name(span: dict) -> str:
        return span.get("font") or ""

    async def parse_pdf(self, file_bytes: bytes) -> tuple[str, List[ParsedSection]]:
        def _sync():
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pages_data = []
            for page in doc:
                blocks = page.get_text("dict")["blocks"]
                page_lines = []
                for block in blocks:
                    if "lines" not in block:
                        continue
                    for line in block["lines"]:
                        text = " ".join(span["text"] for span in line["spans"]).strip()
                        if not text:
                            continue
                        font_size = max(span["size"] for span in line["spans"])
                        is_bold = any(
                            "bold" in self._font_name(span).lower() for span in line["spans"]
                        )
                        page_lines.append(
                            {
                                "text": text,
                                "html": (
                                    f"<p><strong>{escape(text)}</strong></p>"
                                    if is_bold
                                    else f"<p>{escape(text)}</p>"
                                ),
                                "size": font_size,
                                "bold": is_bold,
                                "type": "paragraph",
                            }
                        )
                pages_data.append(page_lines)
            flat = self._split_by_structure(pages_data, source_type="pdf")
            return "pdf", self._flat_dict_to_sections(flat)

        return await asyncio.to_thread(_sync)

    def parse_docx_sync(self, file_bytes: bytes) -> tuple[str, List[ParsedSection]]:
        """Синхронный разбор DOCX (для экспорта в потоке asyncio.to_thread)."""

        def _sync():
            doc = DocxDocument(io.BytesIO(file_bytes))
            doc_type = self._detect_doc_type(doc)
            if doc_type in ("rp", "fos"):
                sections = self._parse_by_word_styles(doc, doc_type)
                if sections:
                    return doc_type, sections
            lines_data = self._extract_lines(doc)
            flat = self._split_by_structure(lines_data, source_type="docx")
            return "generic", self._flat_dict_to_sections(flat)

        return _sync()

    async def parse_docx(self, file_bytes: bytes) -> tuple[str, List[ParsedSection]]:
        def _sync():
            doc = DocxDocument(io.BytesIO(file_bytes))
            doc_type = self._detect_doc_type(doc)
            if doc_type in ("rp", "fos"):
                sections = self._parse_by_word_styles(doc, doc_type)
                if sections:
                    return doc_type, sections
            lines_data = self._extract_lines(doc)
            flat = self._split_by_structure(lines_data, source_type="docx")
            return "generic", self._flat_dict_to_sections(flat)

        return await asyncio.to_thread(_sync)

    def _flat_dict_to_sections(self, flat: Dict[str, str]) -> List[ParsedSection]:
        sections = []
        for idx, (name, content) in enumerate(flat.items()):
            sections.append(
                ParsedSection(
                    section_name=name,
                    content=self._plain_text_to_html(content) if content else content,
                    level=1,
                    order_index=idx,
                    parent_index=None,
                )
            )
        return sections

    def _detect_doc_type(self, doc: DocxDocument) -> str:
        styles = {
            self._style_name(para).lower()
            for para in doc.paragraphs
            if para.text.strip()
        }
        if any("рпд" in s for s in styles):
            return "rp"
        if any("фосд" in s for s in styles):
            return "fos"
        return "generic"

    def _runs_to_html(self, para) -> str:
        parts = []
        for run in para.runs:
            text = run.text
            if not text:
                continue
            chunk = escape(text)
            if run.bold:
                chunk = f"<strong>{chunk}</strong>"
            if run.italic:
                chunk = f"<em>{chunk}</em>"
            if run.underline:
                chunk = f"<u>{chunk}</u>"
            parts.append(chunk)
        return "".join(parts)

    def _paragraph_to_html(self, para) -> str:
        inner = self._runs_to_html(para)
        if not inner.strip():
            inner = escape(para.text)
        if not inner.strip():
            return ""

        style_name = self._style_name(para).lower()
        css: List[str] = []

        if para.paragraph_format.left_indent:
            css.append(f"margin-left: {para.paragraph_format.left_indent.pt:.0f}pt")
        elif "indent" in style_name or "отступ" in style_name:
            css.append("margin-left: 2em")

        if para.alignment == WD_PARAGRAPH_ALIGNMENT.CENTER:
            css.append("text-align: center")
        elif para.alignment == WD_PARAGRAPH_ALIGNMENT.RIGHT:
            css.append("text-align: right")
        elif para.alignment == WD_PARAGRAPH_ALIGNMENT.JUSTIFY:
            css.append("text-align: justify")

        style_attr = f' style="{"; ".join(css)}"' if css else ""

        if "list bullet" in style_name or "маркир" in style_name:
            return f"<ul><li>{inner}</li></ul>"
        if "list number" in style_name or "нумер" in style_name:
            return f"<ol><li>{inner}</li></ol>"

        return f"<p{style_attr}>{inner}</p>"

    def _plain_text_to_html(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        if text.lstrip().startswith("<"):
            return text
        parts = []
        for block in re.split(r"\n\s*\n", text.strip()):
            block = block.strip()
            if not block:
                continue
            if block.lstrip().startswith("<"):
                parts.append(block)
            else:
                inner = escape(block).replace("\n", "<br>")
                parts.append(f"<p>{inner}</p>")
        return "".join(parts)

    def _append_content_html(self, current: dict, html: str) -> None:
        if not html:
            return
        current["content"] = f"{current['content']}{html}"

    def _style_level(self, style_name: str) -> Optional[int]:
        key = (style_name or "").lower().strip()
        for pattern, level in HEADING_STYLE_LEVELS.items():
            if pattern in key:
                return level
        return None

    @staticmethod
    def _looks_like_exam_question_heading(text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", text.strip())
        if not cleaned:
            return False
        if EXAM_QUESTION_HEADING_RE.match(cleaned):
            return True
        body = re.sub(r"^\d+(?:\.\d+)*[\.\)]?\s+", "", cleaned)
        return len(body) < 160 and body.endswith("?")

    @staticmethod
    def _is_major_chapter_heading(text: str) -> bool:
        """«2. ПЕРЕЧЕНЬ…» — глава; «2. Объясните…» — нумерованный вопрос, не глава."""
        cleaned = re.sub(r"\s+", " ", text.strip())
        if DocumentParser._looks_like_exam_question_heading(cleaned):
            return False
        body = re.sub(r"^\d+[\.\)]\s+", "", cleaned)
        if not body:
            return False
        lowered = body.lower()
        if any(keyword in lowered for keyword in MAJOR_SECTION_KEYWORDS):
            return True
        letters = [char for char in body if char.isalpha()]
        if letters:
            upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
            if upper_ratio >= 0.65 and len(body) <= 120:
                return True
        return False

    def _parse_by_word_styles(self, doc: DocxDocument, doc_type: str) -> List[ParsedSection]:
        raw: List[dict] = []
        current: Optional[dict] = None
        started = False

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                from docx.text.paragraph import Paragraph

                para = Paragraph(element, doc)
                text = para.text.strip()
                if not text:
                    continue

                style_name = self._style_name(para)
                level = self._style_level(style_name)

                # x.y.z — всегда 3-й уровень (перекрывает стиль)
                if SUBSUB_PATTERN.match(text) and len(text) < 150 and started:
                    level = 3

                # «6. НАЗВАНИЕ» без подномера — глава, даже если стиль подпунктов
                if (
                    level == 2
                    and re.match(r"^\d+\.\s+(?!\d)", text)
                    and not re.match(r"^\d+\.\d+", text)
                    and self._is_major_chapter_heading(text)
                ):
                    level = 1

                # Нумерованные вопросы экзамена/ФОС не выделяем в отдельные разделы
                if level is not None and self._looks_like_exam_question_heading(text):
                    level = None

                # Продолжение многострочного заголовка (вторая строка без номера)
                if (
                    level
                    and current
                    and current["level"] == level
                    and not CHAPTER_PATTERN.match(text)
                    and not SUBSUB_PATTERN.match(text)
                ):
                    current["section_name"] = f"{current['section_name']} {text}".strip()
                    continue

                if level is not None:
                    if current:
                        raw.append(current)
                    current = {
                        "section_name": re.sub(r"\s+", " ", text),
                        "content": "",
                        "level": level,
                    }
                    started = True
                elif started and current is not None:
                    self._append_content_html(current, self._paragraph_to_html(para))

            elif tag == "tbl" and current is not None:
                from docx.table import Table

                table = Table(element, doc)
                html_table = self._table_to_html_simple(table)
                if html_table:
                    self._append_content_html(current, html_table)

        if current:
            raw.append(current)

        return self._assign_hierarchy(raw)

    def _assign_hierarchy(self, raw: List[dict]) -> List[ParsedSection]:
        sections: List[ParsedSection] = []
        parent_by_level: Dict[int, int] = {}

        for idx, item in enumerate(raw):
            level = item["level"]
            parent_by_level = {lvl: pidx for lvl, pidx in parent_by_level.items() if lvl < level}
            parent_index = parent_by_level.get(level - 1) if level > 1 else None

            sections.append(
                ParsedSection(
                    section_name=item["section_name"],
                    content=self._plain_text_to_html(item["content"].strip())
                    if item["content"].strip() and not item["content"].lstrip().startswith("<")
                    else item["content"].strip(),
                    level=level,
                    order_index=idx,
                    parent_index=parent_index,
                )
            )
            parent_by_level[level] = idx

        return sections

    def _extract_lines(self, doc: DocxDocument) -> List[dict]:
        lines_data = []
        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                from docx.text.paragraph import Paragraph

                para = Paragraph(element, doc)
                text = para.text.strip()
                if not text:
                    continue
                style_name = self._style_name(para).lower()
                is_heading = "heading" in style_name or "заголов" in style_name
                font_size = 12
                is_bold = False
                for run in para.runs:
                    if run.font.size:
                        font_size = max(font_size, run.font.size.pt)
                    if run.bold:
                        is_bold = True
                html = self._paragraph_to_html(para)
                lines_data.append(
                    {
                        "text": text,
                        "html": html or f"<p>{escape(text)}</p>",
                        "size": font_size,
                        "bold": is_bold,
                        "is_heading": is_heading,
                        "style": style_name,
                        "type": "paragraph",
                    }
                )
            elif tag == "tbl":
                from docx.table import Table

                table = Table(element, doc)
                html_table = self._table_to_html_simple(table)
                if html_table:
                    lines_data.append(
                        {
                            "text": html_table,
                            "size": 12,
                            "bold": False,
                            "is_heading": False,
                            "style": "",
                            "type": "table",
                            "html": html_table,
                        }
                    )
        return lines_data

    def _table_to_html_simple(self, table) -> str:
        rows_matrix = []
        seen_rows = set()

        for row in table.rows:
            cells_html = []
            for cell in row.cells:
                parts = [
                    self._paragraph_to_html(p)
                    for p in cell.paragraphs
                    if p.text.strip()
                ]
                cell_html = "".join(parts) if parts else ""
                cells_html.append(cell_html)

            row_key = tuple(cells_html)
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)

            if all(not html.strip() for html in cells_html):
                continue

            rows_matrix.append(cells_html)

        if not rows_matrix:
            return ""

        num_cols = max(len(row) for row in rows_matrix)
        empty_cols = []
        for col_idx in range(num_cols):
            is_empty = all(
                not (row[col_idx].strip() if col_idx < len(row) else "")
                for row in rows_matrix
            )
            if is_empty:
                empty_cols.append(col_idx)

        if empty_cols:
            for row in rows_matrix:
                for col_idx in sorted(empty_cols, reverse=True):
                    if col_idx < len(row):
                        row.pop(col_idx)

        if not rows_matrix or all(len(row) == 0 for row in rows_matrix):
            return ""

        html = [
            '<table class="doc-table" border="1" '
            'style="border-collapse: collapse; width: 100%;">'
        ]
        for row_idx, row in enumerate(rows_matrix):
            if not row:
                continue
            html.append("<tr>")
            for cell_html in row:
                tag = "th" if row_idx == 0 else "td"
                inner = cell_html if cell_html.strip() else "&nbsp;"
                html.append(
                    f'<{tag} style="border: 1px solid #999; padding: 8px; vertical-align: top;">{inner}</{tag}>'
                )
            html.append("</tr>")
        html.append("</table>")
        return "".join(html)

    def _line_to_html(self, line: dict) -> str:
        if line.get("type") == "table":
            return line.get("html", "")
        if line.get("html"):
            return line["html"]
        return self._plain_text_to_html(line.get("text", ""))

    def _split_by_structure(self, lines_data, source_type: str) -> Dict[str, str]:
        all_lines = []
        if source_type == "pdf" and lines_data and isinstance(lines_data[0], list):
            for page_lines in lines_data:
                all_lines.extend(page_lines)
        else:
            all_lines = lines_data

        if not all_lines:
            return {"Документ": "(пустой документ)"}

        sizes = [line["size"] for line in all_lines if line.get("type") == "paragraph"]
        base_size = sorted(sizes)[len(sizes) // 2] if sizes else 12

        heading_indices = []
        for i, line in enumerate(all_lines):
            if line.get("type") == "table":
                continue

            text = line["text"]
            size = line["size"]
            bold = line.get("bold", False)
            is_heading_style = line.get("is_heading", False)

            is_numbered = bool(
                re.match(
                    r"^(\d+[\.\)]\s*\d*[\.\)]?\s*|[Тт]ема\s+\d+|[Рр]аздел\s+\d+|[Гг]лава\s+\d+|[Чч]асть\s+\d+)",
                    text,
                )
            )

            is_large = size >= base_size * 1.3
            is_short = len(text) < 150

            if is_heading_style:
                heading_indices.append(i)
            elif is_short and (is_numbered or (is_large and bold)):
                heading_indices.append(i)

        if not heading_indices:
            if self.custom_sections:
                return self._split_by_keywords(all_lines, self.custom_sections)
            return self._split_by_keywords(all_lines, self.FALLBACK_SECTIONS)

        sections = {}
        for idx, heading_idx in enumerate(heading_indices):
            title = re.sub(r"\s+", " ", all_lines[heading_idx]["text"].strip())
            next_idx = (
                heading_indices[idx + 1] if idx + 1 < len(heading_indices) else len(all_lines)
            )

            content_parts = []
            for j in range(heading_idx + 1, next_idx):
                content_parts.append(self._line_to_html(all_lines[j]))

            content = "".join(content_parts).strip()

            unique_title = title
            counter = 1
            while unique_title in sections:
                unique_title = f"{title} ({counter})"
                counter += 1

            sections[unique_title] = content

        if len(sections) == 1 and not list(sections.values())[0]:
            full_text = "".join(self._line_to_html(line) for line in all_lines)
            return {"Документ": full_text}

        return sections

    def _split_by_keywords(self, lines_data: List[dict], keywords: List[str]) -> Dict[str, str]:
        result = {kw: "" for kw in keywords}
        current = None
        for line in lines_data:
            if line.get("type") == "table":
                if current:
                    result[current] += line["html"]
                continue

            html = line.get("html") or self._plain_text_to_html(line["text"].strip())
            text = line["text"].strip()
            if not text:
                continue
            matched = False
            for kw in keywords:
                pattern = rf"^\s*{re.escape(kw)}\s*[:\.]?\s*$"
                if re.match(pattern, text, re.IGNORECASE):
                    current = kw
                    matched = True
                    break
            if not matched and current:
                result[current] += html

        result = {k: v.strip() for k, v in result.items() if v.strip()}
        if not result:
            full_text = "".join(
                line.get("html") or self._plain_text_to_html(line.get("text", ""))
                for line in lines_data
                if line.get("type") == "table" or line.get("text", "").strip()
            )
            return {"Документ": full_text}
        return result
