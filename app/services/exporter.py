import os
import shutil
import asyncio
from docx import Document as DocxDocument
from app.utils.html_converter import html_to_docx_elements
from app.services.template_manager import get_template_path

class Exporter:
    @staticmethod
    async def export_document(document_id: str, sections_data: dict, template_id: str, output_dir: str) -> str:
        # Получаем путь к шаблону из БД (это асинхронная операция, оставляем как есть)
        template_path = await get_template_path(template_id)
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError("Шаблон не найден")

        output_filename = f"{document_id}.docx"
        output_path = os.path.join(output_dir, output_filename)
        
        # Выносим всю синхронную работу с файлами и python-docx в отдельный поток,
        # чтобы не блокировать асинхронный event loop FastAPI
        def _sync_export():
            # Копируем шаблон в выходной файл
            shutil.copy2(template_path, output_path)
            
            # Открываем скопированный документ
            doc = DocxDocument(output_path)

            # Замена плейсхолдеров в обычных параграфах
            for paragraph in doc.paragraphs:
                for section_name, html_content in sections_data.items():
                    placeholder = f"{{{{{section_name}}}}}"
                    if placeholder in paragraph.text:
                        paragraph.clear()
                        html_to_docx_elements(html_content, doc, parent=paragraph)

            # Также обрабатываем таблицы
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for section_name, html_content in sections_data.items():
                                placeholder = f"{{{{{section_name}}}}}"
                                if placeholder in paragraph.text:
                                    paragraph.clear()
                                    html_to_docx_elements(html_content, doc, parent=paragraph)

            # Сохраняем итоговый документ
            doc.save(output_path)

        # Запускаем синхронную функцию в отдельном потоке
        await asyncio.to_thread(_sync_export)
        
        return output_path