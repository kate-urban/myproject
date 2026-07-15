import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Template

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Макеты из папки Layout/ регистрируются при старте сервера (.docx или .doc).
LAYOUT_TEMPLATES: list[tuple[str, str]] = [
    ("Maket_RPd_FGOS_3.docx", "РПД FGOS 3 (макет)"),
    ("Maket_RPp_FGOS_3.docx", "РПп FGOS 3 (макет)"),
    ("Maket_FOSd_FGOS_3.docx", "ФОС FGOS 3 (макет)"),
    ("Maket_FOSp_FGOS_3.docx", "ФОС практика FGOS 3 (макет)"),
    (
        "B3_01_Gosudarstvennaya_itogovaya_attestatsia_k21.docx",
        "ГИА B3_01 (макет)",
    ),
    (
        "FOS_B3_01_Gosudarstvennaya_itogovaya_attestatsia_k21.docx",
        "ФОС ГИА B3_01 (макет)",
    ),
]


def _templates_dir() -> str:
    default = str(_PROJECT_ROOT / "templates")
    path = os.getenv("TEMPLATES_DIR", default)
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def layout_dir() -> Path:
    default = _PROJECT_ROOT / "Layout"
    return Path(os.getenv("LAYOUT_DIR", str(default))).resolve()


def resolve_layout_file(preferred_filename: str) -> Path | None:
    """Ищет макет в Layout/ по имени (.docx или .doc, по stem)."""
    layout_path = layout_dir()
    if not layout_path.is_dir():
        return None

    direct = layout_path / preferred_filename
    if direct.is_file():
        return direct

    stem = Path(preferred_filename).stem
    for name in (f"{stem}.docx", f"{stem}.doc"):
        candidate = layout_path / name
        if candidate.is_file():
            return candidate

    lowered = stem.lower()
    for path in sorted(layout_path.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".docx", ".doc"}:
            continue
        if path.stem.lower() == lowered or lowered in path.stem.lower():
            return path
    return None


def materialize_layout_docx(source: Path, dest: Path) -> bool:
    """Копирует .docx или конвертирует .doc → .docx в dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".docx":
        shutil.copy2(source, dest)
        return dest.is_file()

    if source.suffix.lower() == ".doc":
        try:
            from app.services.doc_converter import convert_doc_file_to_docx

            convert_doc_file_to_docx(source, dest)
            return dest.is_file()
        except Exception as exc:
            logger.warning("Не удалось конвертировать %s: %s", source.name, exc)
            return False
    return False


async def save_template(file_bytes: bytes, original_filename: str, user_name: str) -> str:
    """Сохраняет загруженный шаблон и возвращает его ID."""
    ext = original_filename.split(".")[-1] if "." in original_filename else "docx"
    new_filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(_templates_dir(), new_filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    async with AsyncSessionLocal() as db:
        template = Template(
            id=uuid.uuid4(),
            name=user_name or original_filename,
            file_path=file_path,
        )
        db.add(template)
        await db.commit()
        return str(template.id)


async def get_template_path(template_id: str) -> Optional[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Template).where(Template.id == template_id))
        template = result.scalar_one_or_none()
        if template and os.path.isfile(template.file_path):
            return template.file_path
        return None


async def get_template_by_name(
    db: AsyncSession,
    display_name: str,
) -> Template | None:
    result = await db.execute(select(Template).where(Template.name == display_name))
    template = result.scalar_one_or_none()
    if template and os.path.isfile(template.file_path):
        return template
    return None


async def list_templates(*, existing_only: bool = True) -> list:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Template).order_by(Template.name))
        templates = result.scalars().all()
        if not existing_only:
            return templates
        return [item for item in templates if os.path.isfile(item.file_path)]


async def seed_layout_templates() -> list[str]:
    """Копирует макеты из Layout/ в templates/ и добавляет/обновляет записи в БД."""
    from app.services.layout_bootstrap import ensure_layout_files

    ensure_layout_files()
    layout_path = layout_dir()
    if not layout_path.is_dir():
        layout_path.mkdir(parents=True, exist_ok=True)
        return []

    registered: list[str] = []
    templates_dir = _templates_dir()

    async with AsyncSessionLocal() as db:
        for filename, display_name in LAYOUT_TEMPLATES:
            source = resolve_layout_file(filename)
            if source is None:
                continue

            dest_name = f"layout_{source.stem}.docx"
            dest_path = Path(os.path.abspath(os.path.join(templates_dir, dest_name)))
            if not materialize_layout_docx(source, dest_path):
                continue

            result = await db.execute(select(Template).where(Template.name == display_name))
            existing = result.scalar_one_or_none()
            if existing:
                existing.file_path = str(dest_path)
            else:
                db.add(
                    Template(
                        id=uuid.uuid4(),
                        name=display_name,
                        file_path=str(dest_path),
                    )
                )
            registered.append(display_name)

        await db.commit()
    return registered


async def list_available_layout_files() -> list[dict[str, str]]:
    """Список файлов в Layout/ для UI/диагностики."""
    layout_path = layout_dir()
    if not layout_path.is_dir():
        return []
    items: list[dict[str, str]] = []
    for preferred, display_name in LAYOUT_TEMPLATES:
        source = resolve_layout_file(preferred)
        items.append(
            {
                "name": display_name,
                "preferred": preferred,
                "found": str(source) if source else "",
                "registered": "yes" if source else "no",
            }
        )
    return items
