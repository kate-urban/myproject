"""Модели по ТЗ: справочники, тело программ, переутверждение, архив, рейтинг."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
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


class RefFgosCompetency(Base):
    """Справочник ФГОС: группа компетенций (УК/ОПК/ПК)."""

    __tablename__ = "ref_fgos_competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(String(8), nullable=False)  # UK, OPK, PK
    code = Column(String(32), nullable=False, unique=True)
    group_code = Column(String(32), nullable=True)
    title = Column(Text, nullable=False)
    fgos_version = Column(String(64), nullable=True)

    indicators = relationship(
        "RefFgosIndicator",
        back_populates="competency",
        cascade="all, delete-orphan",
    )


class RefFgosIndicator(Base):
    __tablename__ = "ref_fgos_indicators"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competency_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ref_fgos_competencies.id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(String(32), nullable=False, unique=True)
    title = Column(Text, nullable=False)

    competency = relationship("RefFgosCompetency", back_populates="indicators")


class RefDepartment(Base):
    """Справочник кафедр с историей (переименования, слияния)."""

    __tablename__ = "ref_departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(16), nullable=False)
    name = Column(String, nullable=False)
    opened_on = Column(Date, nullable=True)
    closed_on = Column(Date, nullable=True)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ref_departments.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("code", "name", "opened_on", name="uq_ref_dept_code_name_from"),
    )


class RefSignature(Base):
    """Подписи для PDF (PNG) + текст для Word."""

    __tablename__ = "ref_signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(64), nullable=False)  # director, dept_head, ...
    full_name = Column(String, nullable=False)
    png_path = Column(String, nullable=True)
    page_hint = Column(String(32), nullable=True)  # title, reapproval
    pos_x_mm = Column(Float, nullable=True)
    pos_y_mm = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class RefPhrase(Base):
    """Версионные стандартные фразы (МТО, аннотации, практики)."""

    __tablename__ = "ref_phrases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    text = Column(Text, nullable=False)
    effective_from = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class RefAbbreviation(Base):
    """Нормализатор сокращений при импорте (ОПР-1 → ОПР)."""

    __tablename__ = "ref_abbreviations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern = Column(String(128), nullable=False)
    replacement = Column(String(128), nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    is_regex = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)


class RefMtoRoom(Base):
    __tablename__ = "ref_mto_rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(32), nullable=False, unique=True)
    name = Column(String, nullable=False)
    equipment = Column(Text, nullable=True)
    building = Column(String, nullable=True)

    program_links = relationship(
        "ProgramMtoRoom",
        back_populates="room",
        cascade="all, delete-orphan",
    )


class ProgramMtoRoom(Base):
    """Связь программы с аудиториями МТО (P3)."""

    __tablename__ = "program_mto_rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    room_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ref_mto_rooms.id", ondelete="CASCADE"),
        nullable=False,
    )

    room = relationship("RefMtoRoom", back_populates="program_links")

    __table_args__ = (
        UniqueConstraint("program_id", "room_id", name="uq_program_mto_room"),
    )


class ProgramTopic(Base):
    """Темы дисциплины (таблицы 3.1 / 3.2)."""

    __tablename__ = "program_topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_number = Column(String(32), nullable=False)
    title = Column(Text, nullable=False)
    semester = Column(Integer, nullable=True)
    hours_lecture = Column(Integer, nullable=True)
    hours_practical = Column(Integer, nullable=True)
    hours_lab = Column(Integer, nullable=True)
    hours_sr = Column(Integer, nullable=True)
    is_bold = Column(Boolean, nullable=False, default=False)
    row_order = Column(Integer, nullable=False, default=0)

    program = relationship("Program", back_populates="topics")

    __table_args__ = (
        UniqueConstraint("program_id", "topic_number", name="uq_program_topics_num"),
    )


class ProgramZuv(Base):
    """З/У/В по индикатору компетенции."""

    __tablename__ = "program_zuv"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    indicator_code = Column(String(32), nullable=False)
    zuv_type = Column(String(16), nullable=False)  # know, skill, ability
    text = Column(Text, nullable=False)
    topic_ref = Column(String(32), nullable=True)
    row_order = Column(Integer, nullable=False, default=0)

    program = relationship("Program", back_populates="zuv_items")


class ProgramLiterature(Base):
    __tablename__ = "program_literature"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    citation = Column(Text, nullable=False)
    lit_type = Column(String(32), nullable=True)  # main, add, electronic
    row_order = Column(Integer, nullable=False, default=0)

    program = relationship("Program", back_populates="literature")


class DirectionProgramLibrary(Base):
    """Библиотека РПД/ФОС на уровне профиля направления (один файл → все годы/формы)."""

    __tablename__ = "direction_program_library"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    discipline_code = Column(String(32), nullable=False)
    doc_kind = Column(String(8), nullable=False)  # rpd | fos
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_hash = Column(String(64), nullable=False)
    source_filename = Column(String, nullable=False)
    extract_json = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "discipline_code",
            "doc_kind",
            name="uq_direction_library_discipline_kind",
        ),
    )


class ProgramAmendment(Base):
    """Листы переутверждения (накопительно по году набора)."""

    __tablename__ = "program_amendments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_year = Column(Integer, nullable=False)
    amendment_kind = Column(String(32), nullable=False)  # none, sheet, full_rewrite
    protocol_ref = Column(String, nullable=True)
    change_summary = Column(Text, nullable=True)
    approved_on = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    program = relationship("Program", back_populates="amendments")


class AuthorLoad(Base):
    """Теневая нагрузка авторов для отчёта по баллам (не в Word)."""

    __tablename__ = "authors_load"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_discipline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_disciplines.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_name = Column(String, nullable=False)
    is_shadow = Column(Boolean, nullable=False, default=False)
    share_percent = Column(Float, nullable=True)
    points_per_credit = Column(Float, nullable=True)
    fixed_points = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "plan_discipline_id",
            "author_name",
            name="uq_authors_load_disc_author",
        ),
    )


class ArchiveVolume(Base):
    __tablename__ = "archive_volumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String, nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    cover_text = Column(Text, nullable=True)
    inventory_text = Column(Text, nullable=True)
    duplex_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship(
        "ArchiveVolumeItem",
        back_populates="volume",
        cascade="all, delete-orphan",
    )


class ArchiveVolumeItem(Base):
    __tablename__ = "archive_volume_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    volume_id = Column(
        UUID(as_uuid=True),
        ForeignKey("archive_volumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet_count = Column(Integer, nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    row_order = Column(Integer, nullable=False, default=0)

    volume = relationship("ArchiveVolume", back_populates="items")
    program = relationship("Program")
