"""DTO учебного плана между reader'ами и writer'ом в БД."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AssessmentDTO:
    form_type: str  # exam | zachet | zachet_graded | kp | kr | control_work
    semester: int | None = None
    course: int | None = None


@dataclass
class DisciplineDTO:
    code: str
    name: str
    in_plan: bool = True
    credits: float | None = None
    hours_total: int | None = None
    hours_contact: int | None = None
    hours_aud: int | None = None
    hours_sr: int | None = None
    hours_control: int | None = None
    department_code: str | None = None
    plx_row_code: str | None = None
    nesting_level: int = 1
    row_order: int = 0
    object_type: str | None = None
    competencies: list[str] = field(default_factory=list)
    assessments: list[AssessmentDTO] = field(default_factory=list)


@dataclass
class StudyPlanDTO:
    source_file: str
    source_format: str  # xml_upvo | plx_excel
    direction_code: str
    direction_name: str
    profile_name: str
    form: str
    year: int | None = None
    qualification: str | None = None
    fgos_number: str | None = None
    disciplines: list[DisciplineDTO] = field(default_factory=list)
