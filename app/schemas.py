from pydantic import BaseModel, UUID4, ConfigDict
from typing import Optional, List
from datetime import datetime

class SectionBase(BaseModel):
    section_name: str
    content: Optional[str] = ""

class SectionUpdate(BaseModel):
    content: Optional[str] = None


class ExportSectionContent(BaseModel):
    id: UUID4
    content: str = ""


class ExportRequest(BaseModel):
    """Актуальное содержимое разделов из редактора (в т.ч. несохранённое)."""
    sections: list[ExportSectionContent] = []

# Настраиваем Pydantic V2 для работы с SQLAlchemy ORM
class SectionOut(SectionBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID4
    document_id: UUID4
    parent_id: Optional[UUID4] = None
    level: int = 1
    order_index: int
    updated_at: Optional[datetime] = None

class TemplateBase(BaseModel):
    name: str

class TemplateOut(TemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID4
    file_path: str
    created_at: datetime


class StudyPlanImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    source_file: str
    source_format: str
    direction_code: str
    direction_name: str
    profile_name: str
    form: str
    year: Optional[int] = None
    disciplines_count: int
    imported_at: datetime


class StudyPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    source_file: str
    source_format: str
    direction_code: str
    direction_name: str
    profile_name: str
    form: str
    year: Optional[int] = None
    disciplines_count: int = 0
    imported_at: datetime


class PlanDisciplineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    code: str
    name: str
    in_plan: bool
    credits: Optional[float] = None
    hours_total: Optional[int] = None
    hours_contact: Optional[int] = None
    hours_aud: Optional[int] = None
    hours_sr: Optional[int] = None
    hours_control: Optional[int] = None
    department_code: Optional[str] = None
    competencies: List[str] = []
    program_status: Optional[str] = None
    document_id: Optional[UUID4] = None
    fos_document_id: Optional[UUID4] = None


class ProgramLinkOut(BaseModel):
    linked: bool
    discipline_code: Optional[str] = None
    plan_discipline_id: Optional[UUID4] = None
    study_plan_id: Optional[UUID4] = None
    program_status: Optional[str] = None
    doc_kind: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None


class ValidationRuleOut(BaseModel):
    rule_id: str
    name: str
    passed: bool
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    skipped: bool = False
    severity: str = "critical"


class DisciplineValidationOut(BaseModel):
    discipline_id: UUID4
    discipline_code: str
    document_id: Optional[UUID4] = None
    passed: bool
    skipped: bool = False
    reason: Optional[str] = None
    results: List[ValidationRuleOut] = []


class PlanValidationOut(BaseModel):
    study_plan_id: UUID4
    total_disciplines: int
    checked: int
    passed: int
    failed: int
    missing_rpd: int
    passed_all: bool
    items: List[DisciplineValidationOut] = []


class FosDisciplineValidationOut(BaseModel):
    discipline_id: UUID4
    discipline_code: str
    rpd_document_id: Optional[UUID4] = None
    fos_document_id: Optional[UUID4] = None
    passed: bool
    skipped: bool = False
    reason: Optional[str] = None
    results: List[ValidationRuleOut] = []


class FosPlanValidationOut(BaseModel):
    study_plan_id: UUID4
    total_disciplines: int
    checked: int
    passed: int
    failed: int
    missing_fos: int
    fos_only: int
    passed_all: bool
    items: List[FosDisciplineValidationOut] = []


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID4
    filename: str
    doc_type: Optional[str] = None
    uploaded_at: datetime
    sections: List[SectionOut] = []
    program_link: Optional[ProgramLinkOut] = None