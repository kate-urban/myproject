import asyncio
import os
import shutil

from docx import Document as DocxDocument

from app.services.export_by_headings import inject_sections_by_headings
from app.services.template_manager import get_template_path
from app.utils.html_converter import html_to_docx_elements


class Exporter:
    @staticmethod
    async def export_document(
        document_id: str,
        sections_data: dict,
        template_id: str,
        output_dir: str,
    ) -> str:
        template_path = await get_template_path(template_id)
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError("Шаблон не найден")

        output_filename = f"{document_id}.docx"
        output_path = os.path.join(output_dir, output_filename)

        def _sync_export():
            shutil.copy2(template_path, output_path)
            doc = DocxDocument(output_path)

            placeholder_hits = Exporter._replace_placeholders(doc, sections_data)
            heading_hits = 0
            if placeholder_hits == 0:
                heading_hits = inject_sections_by_headings(doc, sections_data)

            doc.save(output_path)
            return {
                "placeholders": placeholder_hits,
                "injected": heading_hits,
            }

        stats = await asyncio.to_thread(_sync_export)
        return output_path, stats

    @staticmethod
    def _replace_placeholders(doc: DocxDocument, sections_data: dict) -> int:
        hits = 0

        for paragraph in doc.paragraphs:
            hits += Exporter._replace_in_paragraph(paragraph, doc, sections_data)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        hits += Exporter._replace_in_paragraph(paragraph, doc, sections_data)

        return hits

    @staticmethod
    def _replace_in_paragraph(paragraph, doc: DocxDocument, sections_data: dict) -> int:
        hits = 0
        for section_name, html_content in sections_data.items():
            placeholder = f"{{{{{section_name}}}}}"
            if placeholder in paragraph.text:
                paragraph.clear()
                html_to_docx_elements(html_content, doc, parent=paragraph)
                hits += 1
        return hits
