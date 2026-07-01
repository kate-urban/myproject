from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    doc_type = Column(String, nullable=True)  # rp, fos, generic
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

class Section(Base):
    __tablename__ = "sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    parent_id = Column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="SET NULL"), nullable=True)
    section_name = Column(String, nullable=False)
    content = Column(Text, default="")          # HTML-текст
    content_plain = Column(Text, default="")    # текст без разметки для поиска
    level = Column(Integer, default=1)          # 1=глава, 2=подглава, 3=под-подглава
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Template(Base):
    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)  # путь к .docx шаблону
    created_at = Column(DateTime(timezone=True), server_default=func.now())