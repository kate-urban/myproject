from pydantic import BaseModel, UUID4, ConfigDict
from typing import Optional, List
from datetime import datetime

class SectionBase(BaseModel):
    section_name: str
    content: Optional[str] = ""

class SectionUpdate(BaseModel):
    content: Optional[str] = None

# Настраиваем Pydantic V2 для работы с SQLAlchemy ORM
class SectionOut(SectionBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID4
    document_id: UUID4
    parent_id: Optional[UUID4] = None
    level: int = 1
    order_index: int
    updated_at: Optional[datetime] = None

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID4
    filename: str
    doc_type: Optional[str] = None
    uploaded_at: datetime
    sections: List[SectionOut] = []

class TemplateBase(BaseModel):
    name: str

class TemplateOut(TemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID4
    file_path: str
    created_at: datetime