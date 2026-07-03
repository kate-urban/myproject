import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    UUID,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

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


class Direction(Base):
    __tablename__ = "directions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(16), nullable=False, unique=True)
    name = Column(String, nullable=False)

    profiles = relationship("Profile", back_populates="direction")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    direction_id = Column(
        UUID(as_uuid=True), ForeignKey("directions.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("direction_id", "name", name="uq_profiles_direction_name"),
    )

    direction = relationship("Direction", back_populates="profiles")
    study_plans = relationship("StudyPlan", back_populates="profile")


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_file = Column(String, nullable=False)
    source_format = Column(String(32), nullable=False)  # xml_upvo | plx_excel
    form = Column(String(32), nullable=False)  # ochnaya | ochno_zaochnaya | ...
    year = Column(Integer, nullable=True)
    qualification = Column(String, nullable=True)
    fgos_number = Column(String, nullable=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("profile_id", "year", "form", name="uq_study_plans_profile_year_form"),
    )

    profile = relationship("Profile", back_populates="study_plans")
    disciplines = relationship(
        "PlanDiscipline", back_populates="study_plan", cascade="all, delete-orphan"
    )


class PlanDiscipline(Base):
    __tablename__ = "plan_disciplines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(String(32), nullable=False)
    name = Column(String, nullable=False)
    in_plan = Column(Boolean, nullable=False, default=True)
    credits = Column(Float, nullable=True)
    hours_total = Column(Integer, nullable=True)
    hours_contact = Column(Integer, nullable=True)
    hours_aud = Column(Integer, nullable=True)
    hours_sr = Column(Integer, nullable=True)
    hours_control = Column(Integer, nullable=True)
    department_code = Column(String(16), nullable=True)
    plx_row_code = Column(String(16), nullable=True)
    nesting_level = Column(Integer, nullable=False, default=1)
    row_order = Column(Integer, nullable=False, default=0)
    object_type = Column(String(8), nullable=True)

    __table_args__ = (
        UniqueConstraint("study_plan_id", "code", name="uq_plan_disciplines_plan_code"),
    )

    study_plan = relationship("StudyPlan", back_populates="disciplines")
    competencies = relationship(
        "PlanDisciplineCompetency",
        back_populates="discipline",
        cascade="all, delete-orphan",
    )
    program = relationship(
        "Program", back_populates="discipline", uselist=False, cascade="all, delete-orphan"
    )


class PlanDisciplineCompetency(Base):
    __tablename__ = "plan_discipline_competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_discipline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_disciplines.id", ondelete="CASCADE"),
        nullable=False,
    )
    competency_code = Column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "plan_discipline_id",
            "competency_code",
            name="uq_plan_disc_competencies_disc_code",
        ),
    )

    discipline = relationship("PlanDiscipline", back_populates="competencies")


class Program(Base):
    __tablename__ = "programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_discipline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_disciplines.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String(32), nullable=False, default="missing")
    rpd_discipline_code = Column(String(32), nullable=True)
    rpd_discipline_name = Column(String, nullable=True)
    rpd_direction_code = Column(String(16), nullable=True)
    rpd_profile_name = Column(String, nullable=True)
    rpd_department_code = Column(String(16), nullable=True)
    rpd_hours_total = Column(Integer, nullable=True)
    rpd_credits = Column(Float, nullable=True)
    rpd_competencies = Column(Text, nullable=True)
    rpd_extract_json = Column(Text, nullable=True)
    fos_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    fos_extract_json = Column(Text, nullable=True)

    discipline = relationship("PlanDiscipline", back_populates="program")
    document = relationship("Document", foreign_keys=[document_id])
    fos_document = relationship("Document", foreign_keys=[fos_document_id])