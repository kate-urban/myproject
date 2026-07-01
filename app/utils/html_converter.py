from bs4 import BeautifulSoup, Tag
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

def html_to_docx_elements(html: str, doc: Document, parent=None):
    """
    Рекурсивно обходит HTML-дерево и добавляет элементы в docx-документ.
    """
    soup = BeautifulSoup(html, 'html.parser')   # или 'html5lib', если установили
    _process_node(soup, doc, parent)

def _process_node(node, doc, parent_paragraph=None):
    if node is None:
        return
    if isinstance(node, str):
        # Текстовая строка – добавляем в текущий параграф (или создаём новый)
        if parent_paragraph is None:
            parent_paragraph = doc.add_paragraph()
        parent_paragraph.add_run(node.strip())
        return

    if not isinstance(node, Tag):
        return

    # Обработка тегов
    tag = node.name.lower()

    if tag == 'p':
        p = doc.add_paragraph()
        for child in node.children:
            _process_node(child, doc, p)
    elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        p = doc.add_paragraph()
        run = p.add_run(node.get_text(strip=True))
        # Задаём размер шрифта в зависимости от уровня
        size_map = {'h1': 24, 'h2': 20, 'h3': 16, 'h4': 14, 'h5': 12, 'h6': 10}
        run.font.size = Pt(size_map.get(tag, 12))
        run.bold = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if tag == 'h1' else None
    elif tag == 'b' or tag == 'strong':
        # Жирный текст внутри текущего параграфа
        if parent_paragraph is None:
            p = doc.add_paragraph()
        else:
            p = parent_paragraph
        run = p.add_run(node.get_text())
        run.bold = True
        # Если есть дети, обрабатываем их рекурсивно (но обычно внутри просто текст)
    elif tag == 'i' or tag == 'em':
        if parent_paragraph is None:
            p = doc.add_paragraph()
        else:
            p = parent_paragraph
        run = p.add_run(node.get_text())
        run.italic = True
    elif tag == 'u':
        if parent_paragraph is None:
            p = doc.add_paragraph()
        else:
            p = parent_paragraph
        run = p.add_run(node.get_text())
        run.underline = True
    elif tag == 'br':
        if parent_paragraph is None:
            p = doc.add_paragraph()
        else:
            p = parent_paragraph
        p.add_run().add_break()
    elif tag == 'ul' or tag == 'ol':
        # Списки
        for li in node.find_all('li', recursive=False):
            p = doc.add_paragraph(style='List Bullet' if tag == 'ul' else 'List Number')
            # Обрабатываем содержимое li
            for child in li.children:
                _process_node(child, doc, p)
    elif tag == 'li':
        # Если li встретился без ul/ol (обрабатывается внутри списка)
        pass
    elif tag == 'table':
        # Простая конвертация таблицы
        rows = node.find_all('tr')
        if rows:
            table = doc.add_table(rows=len(rows), cols=len(rows[0].find_all(['td', 'th'])))
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                for j, cell in enumerate(cells):
                    table.cell(i, j).text = cell.get_text(strip=True)
    else:
        # Прочие теги – игнорируем, но проходим по детям
        for child in node.children:
            _process_node(child, doc, parent_paragraph)