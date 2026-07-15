import asyncio
import os
import shutil

from docx import Document as DocxDocument

from app.services.export_assemble import assemble_document_from_sections, detect_template_kind
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
        *,
        sections_order: list[str] | None = None,
        doc_type: str | None = None,
        template_name: str | None = None,
    ) -> tuple[str, dict]:
        template_path = await get_template_path(template_id)
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError("Шаблон не найден")

        output_filename = f"{document_id}.docx"
        output_path = os.path.join(output_dir, output_filename)

        ordered_sections = Exporter._ordered_sections(sections_data, sections_order)

        def _sync_export():
            shutil.copy2(template_path, output_path)
            doc = DocxDocument(output_path)

            placeholder_hits = Exporter._replace_placeholders(doc, sections_data)
            heading_hits = 0
            assembled_hits = 0
            mode = "placeholders"

            template_kind = detect_template_kind(doc)
            is_fos = (
                doc_type == "fos"
                or (template_name and "ФОС" in template_name.upper())
                or template_kind == "fos"
            )

            if placeholder_hits == 0 and not is_fos:
                heading_hits = inject_sections_by_headings(doc, sections_data)
                mode = "headings"

            total_with_content = len(ordered_sections)
            need_assemble = is_fos or (
                placeholder_hits == 0
                and heading_hits < max(1, int(total_with_content * 0.4))
            )

            if need_assemble and ordered_sections:
                assembled_hits = assemble_document_from_sections(
                    doc,
                    ordered_sections,
                    template_kind=template_kind,
                )
                mode = "assemble"

            doc.save(output_path)
            return {
                "placeholders": placeholder_hits,
                "injected": heading_hits or assembled_hits,
                "assembled": assembled_hits,
                "mode": mode,
                "sections_total": total_with_content,
            }

        stats = await asyncio.to_thread(_sync_export)
        return output_path, stats

    @staticmethod
    def _ordered_sections(
        sections_data: dict,
        sections_order: list[str] | None,
    ) -> list[tuple[str, str]]:
        if sections_order:
            return [
                (name, sections_data[name])
                for name in sections_order
                if name in sections_data and sections_data[name] and str(sections_data[name]).strip()
            ]
        return [
            (name, content)
            for name, content in sections_data.items()
            if content and str(content).strip()
        ]

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
