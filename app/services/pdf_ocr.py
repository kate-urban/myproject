"""OCR fallback для legacy PDF (ТЗ п. 1.4, P1)."""

from __future__ import annotations

import io
import os
import shutil


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None or bool(os.getenv("TESSERACT_CMD"))


def extract_text_from_pdf_ocr(file_bytes: bytes, *, max_pages: int = 8) -> str:
    """Извлекает текст из PDF через OCR; пустая строка если OCR недоступен."""
    if not ocr_available():
        return ""

    import fitz
    import pytesseract
    from PIL import Image

    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    lang = os.getenv("OCR_LANG", "rus+eng")
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    chunks: list[str] = []
    for page_index, page in enumerate(doc):
        if page_index >= max_pages:
            break
        pix = page.get_pixmap(dpi=200, alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(image, lang=lang)
        if text.strip():
            chunks.append(text)
    return "\n".join(chunks)
