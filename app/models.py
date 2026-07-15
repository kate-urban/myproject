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
    source_path = Column(String, nullable=True)  # исходный .docx для инкрементального экспорта
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
    folder_path = Column(String, nullable=True)  # путь в «УЧЕБНЫЕ ПЛАНЫ», напр. ОЧНОЕ ОБУЧЕНИЕ/Магистры/ИЛиП/2026
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
    cycle_identifier = Column(String(32), nullable=True)
    block_type = Column(String(32), nullable=True)
    block_code = Column(String(16), nullable=True)

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
    assessments = relationship(
        "PlanDisciplineAssessment",
        back_populates="discipline",
        cascade="all, delete-orphan",
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


class PlanDisciplineAssessment(Base):
    """Формы аттестации из учебного плана (семестр + тип)."""

    __tablename__ = "plan_discipline_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_discipline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_disciplines.id", ondelete="CASCADE"),
        nullable=False,
    )
    form_type = Column(String(32), nullable=False)
    semester = Column(Integer, nullable=True)
    course = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "plan_discipline_id",
            "form_type",
            "semester",
            "course",
            name="uq_plan_disc_assessment",
        ),
    )

    discipline = relationship("PlanDiscipline", back_populates="assessments")


class ProgramStructuredRpd(Base):
    """Нормализованный снимок extract РПД (этап 2, параллельно HTML)."""

    __tablename__ = "program_structured_rpd"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    payload_json = Column(Text, nullable=False)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program", back_populates="structured_rpd")


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
    program_kind = Column(String(16), nullable=False, default="discipline")  # discipline|practice|gia
    is_archived = Column(Boolean, nullable=False, default=False)
    constructor_json = Column(Text, nullable=True)

    discipline = relationship("PlanDiscipline", back_populates="program")
    document = relationship("Document", foreign_keys=[document_id])
    fos_document = relationship("Document", foreign_keys=[fos_document_id])
    structured_rpd = relationship(
        "ProgramStructuredRpd",
        back_populates="program",
        uselist=False,
        cascade="all, delete-orphan",
    )
    topics = relationship(
        "ProgramTopic",
        back_populates="program",
        cascade="all, delete-orphan",
        foreign_keys="ProgramTopic.program_id",
    )
    zuv_items = relationship(
        "ProgramZuv",
        back_populates="program",
        cascade="all, delete-orphan",
        foreign_keys="ProgramZuv.program_id",
    )
    literature = relationship(
        "ProgramLiterature",
        back_populates="program",
        cascade="all, delete-orphan",
        foreign_keys="ProgramLiterature.program_id",
    )
    amendments = relationship(
        "ProgramAmendment",
        back_populates="program",
        cascade="all, delete-orphan",
        foreign_keys="ProgramAmendment.program_id",
    )
    validation_waivers = relationship(
        "ValidationWaiver",
        back_populates="program",
        cascade="all, delete-orphan",
    )


class ValidationWaiver(Base):
    """Ручное снятие ошибки сверки без правки документа."""

    __tablename__ = "validation_waivers"
    __table_args__ = (
        UniqueConstraint(
            "program_id",
            "doc_kind",
            "rule_id",
            name="uq_validation_waiver_program_kind_rule",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    doc_kind = Column(String(8), nullable=False)  # rpd | fos
    rule_id = Column(String(16), nullable=False)
    comment = Column(Text, nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program", back_populates="validation_waivers")


class AdminUser(Base):
    """Единственная роль системы — администратор (методист УМУ)."""

    __tablename__ = "admin_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(128), nullable=False)
    password_hash = Column(String(256), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EditLock(Base):
    """Блокировка записи при одновременной работе двух администраторов."""

    __tablename__ = "edit_locks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type = Column(String(32), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_display_name = Column(String(128), nullable=False)
    session_token = Column(String(64), nullable=False, unique=True)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_edit_locks_resource"),
    )

    user = relationship("AdminUser")


class ExportJob(Base):
    """Журнал экспортов DOCX (после сверки или из редактора)."""

    __tablename__ = "export_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("study_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    plan_discipline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_disciplines.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    doc_kind = Column(String(8), nullable=False, default="rpd")
    output_filename = Column(String(512), nullable=False)
    validation_passed = Column(Boolean, nullable=True)
    export_mode = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


import app.models_tz  # noqa: E402, F401