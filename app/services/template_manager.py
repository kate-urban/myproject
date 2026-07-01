import os
import shutil
import uuid
from typing import Optional
from app.models import Template
from app.database import AsyncSessionLocal
from sqlalchemy import select

TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "./templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

async def save_template(file_bytes: bytes, original_filename: str, user_name: str) -> str:
    """Сохраняет загруженный шаблон и возвращает его ID"""
    # Генерируем уникальное имя файла
    ext = original_filename.split('.')[-1] if '.' in original_filename else 'docx'
    new_filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(TEMPLATES_DIR, new_filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Сохраняем запись в БД
    async with AsyncSessionLocal() as db:
        template = Template(
            id=uuid.uuid4(),
            name=user_name or original_filename,
            file_path=file_path
        )
        db.add(template)
        await db.commit()
        return str(template.id)

async def get_template_path(template_id: str) -> Optional[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Template).where(Template.id == template_id))
        template = result.scalar_one_or_none()
        return template.file_path if template else None

async def list_templates() -> list:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Template))
        return result.scalars().all()