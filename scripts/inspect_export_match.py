"""Временный скрипт: сопоставление разделов РПД и заголовков макета."""
import asyncio
import re
from pathlib import Path

from docx import Document

from app.services.parser import DocumentParser

RPD_SAMPLE = Path("samples/B1_O_01_07_Proektnaya_deyatelnost_k55.docx")
MAKET_RPD = Path("Layout/Maket_RPd_FGOS_3.docx")


def normalize_heading(text: str) -> str:
    t = re.sub(r"\s+", " ", text.strip().lower())
    t = re.sub(r"^\d+[\.)]\s*", "", t)
    return t


async def main() -> None:
    data = RPD_SAMPLE.read_bytes()
    _, sections = await DocumentParser().parse_docx(data)
    section_names = [s.section_name for s in sections]

    maket = Document(MAKET_RPD)
    headings = []
    for para in maket.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if "heading" in style.lower() or re.match(r"^\d+[\.)]", text):
            headings.append(text)

    print("=== Parsed RPD sections:", len(section_names), "===")
    for name in section_names[:20]:
        print(" ", repr(name))
    if len(section_names) > 20:
        print(" ...", len(section_names) - 20, "more")

    print("\n=== Maket headings:", len(headings), "===")
    for h in headings[:20]:
        print(" ", repr(h))

    section_norm = {normalize_heading(n): n for n in section_names}
    matched = 0
    for h in headings:
        if normalize_heading(h) in section_norm:
            matched += 1
    print(f"\nRough heading matches: {matched}/{len(headings)}")


if __name__ == "__main__":
    asyncio.run(main())
