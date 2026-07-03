from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.shared import Pt
from docx.text.paragraph import Paragraph


def _insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return Paragraph(new_p, paragraph._parent)


def html_to_docx_elements(html: str, doc: Document, parent=None):
    """Обходит HTML и добавляет элементы в docx-документ."""
    soup = BeautifulSoup(html or "", "html.parser")
    if parent is None:
        _process_node(soup, doc, None)
        return
    insert_html_after_paragraph(doc, parent, html, replace_anchor=True)


def insert_html_after_paragraph(
    doc: Document,
    anchor: Paragraph,
    html: str,
    *,
    replace_anchor: bool = False,
) -> Paragraph:
    """Вставляет HTML начиная с anchor (заменяя его содержимое или добавляя после)."""
    soup = BeautifulSoup(html or "", "html.parser")
    blocks = [
        node
        for node in soup.children
        if not (isinstance(node, NavigableString) and not str(node).strip())
    ]
    if not blocks:
        if replace_anchor:
            anchor.clear()
        return anchor

    current = anchor
    first = True
    for block in blocks:
        if first and replace_anchor:
            current.clear()
            _render_block(block, doc, current)
            first = False
            continue
        current = _insert_paragraph_after(current)
        _render_block(block, doc, current)
        first = False
    return current


def _render_block(node, doc: Document, paragraph: Paragraph) -> None:
    if isinstance(node, NavigableString):
        text = str(node).strip()
        if text:
            paragraph.add_run(text)
        return
    if not isinstance(node, Tag):
        return

    tag = node.name.lower()
    if tag == "p":
        for child in node.children:
            _process_node(child, doc, paragraph)
    elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        run = paragraph.add_run(node.get_text(strip=True))
        size_map = {"h1": 24, "h2": 20, "h3": 16, "h4": 14, "h5": 12, "h6": 10}
        run.font.size = Pt(size_map.get(tag, 12))
        run.bold = True
        if tag == "h1":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif tag in ("ul", "ol"):
        for li in node.find_all("li", recursive=False):
            list_paragraph = _insert_paragraph_after(paragraph)
            list_paragraph.style = "List Bullet" if tag == "ul" else "List Number"
            for child in li.children:
                _process_node(child, doc, list_paragraph)
    elif tag == "table":
        rows = node.find_all("tr")
        if rows:
            cols = max(len(row.find_all(["td", "th"])) for row in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            for i, row in enumerate(rows):
                cells = row.find_all(["td", "th"])
                for j, cell in enumerate(cells):
                    table.cell(i, j).text = cell.get_text(strip=True)
    else:
        for child in node.children:
            _process_node(child, doc, paragraph)


def _process_node(node, doc, parent_paragraph=None):
    if node is None:
        return
    if isinstance(node, NavigableString):
        text = str(node).strip()
        if not text:
            return
        if parent_paragraph is None:
            parent_paragraph = doc.add_paragraph()
        parent_paragraph.add_run(text)
        return

    if not isinstance(node, Tag):
        return

    tag = node.name.lower()

    if tag == "p":
        p = doc.add_paragraph()
        for child in node.children:
            _process_node(child, doc, p)
    elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        p = doc.add_paragraph()
        run = p.add_run(node.get_text(strip=True))
        size_map = {"h1": 24, "h2": 20, "h3": 16, "h4": 14, "h5": 12, "h6": 10}
        run.font.size = Pt(size_map.get(tag, 12))
        run.bold = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if tag == "h1" else None
    elif tag in ("b", "strong"):
        p = parent_paragraph or doc.add_paragraph()
        run = p.add_run(node.get_text())
        run.bold = True
    elif tag in ("i", "em"):
        p = parent_paragraph or doc.add_paragraph()
        run = p.add_run(node.get_text())
        run.italic = True
    elif tag == "u":
        p = parent_paragraph or doc.add_paragraph()
        run = p.add_run(node.get_text())
        run.underline = True
    elif tag == "br":
        p = parent_paragraph or doc.add_paragraph()
        p.add_run().add_break()
    elif tag in ("ul", "ol"):
        for li in node.find_all("li", recursive=False):
            p = doc.add_paragraph(style="List Bullet" if tag == "ul" else "List Number")
            for child in li.children:
                _process_node(child, doc, p)
    elif tag == "table":
        rows = node.find_all("tr")
        if rows:
            cols = max(len(row.find_all(["td", "th"])) for row in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            for i, row in enumerate(rows):
                cells = row.find_all(["td", "th"])
                for j, cell in enumerate(cells):
                    table.cell(i, j).text = cell.get_text(strip=True)
    else:
        for child in node.children:
            _process_node(child, doc, parent_paragraph)
