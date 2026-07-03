import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Template

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Макеты из папки Layout регистрируются при старте сервера.
LAYOUT_TEMPLATES: list[tuple[str, str]] = [
    ("Maket_RPd_FGOS_3.docx", "РПД FGOS 3 (макет)"),
    ("Maket_FOSd_FGOS_3.docx", "ФОС FGOS 3 (макет)"),
]


def _templates_dir() -> str:
    default = str(_PROJECT_ROOT / "templates")
    path = os.getenv("TEMPLATES_DIR", default)
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def _layout_dir() -> Path:
    default = _PROJECT_ROOT / "Layout"
    return Path(os.getenv("LAYOUT_DIR", str(default))).resolve()


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


async def list_templates(*, existing_only: bool = True) -> list:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Template).order_by(Template.name))
        templates = result.scalars().all()
        if not existing_only:
            return templates
        return [item for item in templates if os.path.isfile(item.file_path)]


async def seed_layout_templates() -> list[str]:
    """Копирует макеты из Layout/ в templates/ и добавляет/обновляет записи в БД."""
    layout_path = _layout_dir()
    if not layout_path.is_dir():
        return []

    registered: list[str] = []
    templates_dir = _templates_dir()

    async with AsyncSessionLocal() as db:
        for filename, display_name in LAYOUT_TEMPLATES:
            source = layout_path / filename
            if not source.is_file():
                continue

            dest_name = f"layout_{filename}"
            dest_path = os.path.abspath(os.path.join(templates_dir, dest_name))
            shutil.copy2(source, dest_path)

            result = await db.execute(select(Template).where(Template.name == display_name))
            existing = result.scalar_one_or_none()
            if existing:
                existing.file_path = dest_path
            else:
                db.add(
                    Template(
                        id=uuid.uuid4(),
                        name=display_name,
                        file_path=dest_path,
                    )
                )
            registered.append(display_name)

        await db.commit()
    return registered
