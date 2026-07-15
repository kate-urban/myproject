"""Запись StudyPlanDTO в PostgreSQL."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Direction,
    PlanDiscipline,
    PlanDisciplineAssessment,
    PlanDisciplineCompetency,
    Profile,
    Program,
    StudyPlan,
)
from app.services.importers.dto import AssessmentDTO, DisciplineDTO, StudyPlanDTO
from app.services.importers.plx_excel import PlxExcelReader
from app.services.importers.plx_xml import PlxXmlReader
from app.services.text_normalizer import normalize_study_plan_dto
from app.utils.discipline_bucket import classify_discipline_bucket


def _discipline_richness(item: DisciplineDTO) -> tuple[int, float, int, int]:
    return (
        item.hours_total or 0,
        item.credits or 0.0,
        len(item.competencies),
        item.row_order,
    )


def _merge_assessments(
    left: list[AssessmentDTO], right: list[AssessmentDTO]
) -> list[AssessmentDTO]:
    seen: set[tuple[str, int | None, int | None]] = set()
    merged: list[AssessmentDTO] = []
    for item in [*left, *right]:
        key = (item.form_type, item.semester, item.course)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_discipline_dtos(left: DisciplineDTO, right: DisciplineDTO) -> DisciplineDTO:
    keep, other = (
        (left, right) if _discipline_richness(left) >= _discipline_richness(right) else (right, left)
    )
    name = keep.name if len(keep.name) >= len(other.name) else other.name
    return DisciplineDTO(
        code=keep.code,
        name=name,
        in_plan=keep.in_plan or other.in_plan,
        credits=keep.credits if keep.credits is not None else other.credits,
        hours_total=keep.hours_total if keep.hours_total is not None else other.hours_total,
        hours_contact=keep.hours_contact if keep.hours_contact is not None else other.hours_contact,
        hours_aud=keep.hours_aud if keep.hours_aud is not None else other.hours_aud,
        hours_sr=keep.hours_sr if keep.hours_sr is not None else other.hours_sr,
        hours_control=keep.hours_control if keep.hours_control is not None else other.hours_control,
        department_code=keep.department_code or other.department_code,
        plx_row_code=keep.plx_row_code or other.plx_row_code,
        nesting_level=min(keep.nesting_level, other.nesting_level),
        row_order=min(keep.row_order, other.row_order),
        object_type=keep.object_type or other.object_type,
        competencies=sorted(set(keep.competencies) | set(other.competencies)),
        assessments=_merge_assessments(keep.assessments, other.assessments),
    )


def dedupe_discipline_dtos(items: list[DisciplineDTO]) -> list[DisciplineDTO]:
    """UpVo иногда даёт одну дисциплину в нескольких строках с одним кодом."""
    by_code: dict[str, DisciplineDTO] = {}
    for item in sorted(items, key=lambda d: (d.row_order, d.nesting_level, d.code)):
        existing = by_code.get(item.code)
        by_code[item.code] = _merge_discipline_dtos(existing, item) if existing else item
    return sorted(by_code.values(), key=lambda d: (d.row_order, d.code))


class StudyPlanImporter:
    def __init__(self) -> None:
        self._xml_reader = PlxXmlReader()
        self._excel_reader = PlxExcelReader()

    def read_dto(
        self,
        path: str | Path | None = None,
        *,
        content: bytes | None = None,
        filename: str | None = None,
    ) -> StudyPlanDTO:
        if content is not None:
            name = filename or "upload"
            suffix = Path(name).suffix.lower()
            if suffix in (".xlsx", ".xlsm"):
                return self._excel_reader.read_bytes(content, name)
            if suffix == ".plx":
                return self._read_plx_bytes(content, name)
            raise ValueError(
                f"Формат {suffix} не поддержан. Доступны: .plx, .xlsx."
            )

        if path is None:
            raise ValueError("Укажите path или content")

        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".plx":
            return self._xml_reader.read(file_path)
        if suffix in (".xlsx", ".xlsm"):
            return self._excel_reader.read(file_path)
        raise ValueError(
            f"Формат {suffix} не поддержан. Доступны: .plx (XML UpVo), .xlsx."
        )

    def _read_plx_bytes(self, content: bytes, filename: str) -> StudyPlanDTO:
        import tempfile

        suffix = Path(filename).suffix or ".plx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            dto = self._xml_reader.read(tmp_path)
            dto.source_file = filename
            return dto
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def import_file(
        self,
        path: str | Path | None = None,
        db: AsyncSession | None = None,
        *,
        content: bytes | None = None,
        filename: str | None = None,
        folder_path: str | None = None,
    ) -> StudyPlan:
        if db is None:
            raise ValueError("db session is required")
        dto = self.read_dto(path, content=content, filename=filename)
        dto = await normalize_study_plan_dto(db, dto)
        return await self.import_dto(dto, db, folder_path=folder_path)

    async def import_dto(
        self,
        dto: StudyPlanDTO,
        db: AsyncSession,
        *,
        folder_path: str | None = None,
    ) -> StudyPlan:
        direction = await self._get_or_create_direction(db, dto)
        profile = await self._get_or_create_profile(db, direction, dto)
        plan = await self._upsert_study_plan(db, profile, dto, folder_path=folder_path)
        await self._replace_disciplines(db, plan, dto)
        await db.commit()
        await db.refresh(plan)
        return plan

    async def _get_or_create_direction(
        self, db: AsyncSession, dto: StudyPlanDTO
    ) -> Direction:
        result = await db.execute(
            select(Direction).where(Direction.code == dto.direction_code)
        )
        direction = result.scalar_one_or_none()
        if direction:
            if dto.direction_name and direction.name != dto.direction_name:
                direction.name = dto.direction_name
            return direction

        direction = Direction(code=dto.direction_code, name=dto.direction_name)
        db.add(direction)
        await db.flush()
        return direction

    async def _get_or_create_profile(
        self, db: AsyncSession, direction: Direction, dto: StudyPlanDTO
    ) -> Profile:
        result = await db.execute(
            select(Profile).where(
                Profile.direction_id == direction.id,
                Profile.name == dto.profile_name,
            )
        )
        profile = result.scalar_one_or_none()
        if profile:
            return profile

        profile = Profile(direction_id=direction.id, name=dto.profile_name)
        db.add(profile)
        await db.flush()
        return profile

    async def _upsert_study_plan(
        self,
        db: AsyncSession,
        profile: Profile,
        dto: StudyPlanDTO,
        *,
        folder_path: str | None = None,
    ) -> StudyPlan:
        result = await db.execute(
            select(StudyPlan).where(
                StudyPlan.profile_id == profile.id,
                StudyPlan.year == dto.year,
                StudyPlan.form == dto.form,
            )
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            plan = StudyPlan(
                id=uuid.uuid4(),
                profile_id=profile.id,
                source_file=dto.source_file,
                source_format=dto.source_format,
                folder_path=folder_path,
                form=dto.form,
                year=dto.year,
                qualification=dto.qualification,
                fgos_number=dto.fgos_number,
            )
            db.add(plan)
        else:
            plan.source_file = dto.source_file
            plan.source_format = dto.source_format
            if folder_path:
                plan.folder_path = folder_path
            plan.qualification = dto.qualification
            plan.fgos_number = dto.fgos_number

        await db.flush()
        return plan

    async def _replace_disciplines(
        self, db: AsyncSession, plan: StudyPlan, dto: StudyPlanDTO
    ) -> None:
        old_discipline_ids = (
            await db.execute(
                select(PlanDiscipline.id).where(
                    PlanDiscipline.study_plan_id == plan.id
                )
            )
        ).scalars().all()

        if old_discipline_ids:
            await db.execute(
                delete(PlanDisciplineAssessment).where(
                    PlanDisciplineAssessment.plan_discipline_id.in_(
                        old_discipline_ids
                    )
                )
            )
            await db.execute(
                delete(PlanDisciplineCompetency).where(
                    PlanDisciplineCompetency.plan_discipline_id.in_(
                        old_discipline_ids
                    )
                )
            )
            await db.execute(
                delete(Program).where(Program.plan_discipline_id.in_(old_discipline_ids))
            )
            await db.execute(
                delete(PlanDiscipline).where(PlanDiscipline.id.in_(old_discipline_ids))
            )
            await db.flush()

        disciplines = dedupe_discipline_dtos(dto.disciplines)
        for item in disciplines:
            discipline = PlanDiscipline(
                id=uuid.uuid4(),
                study_plan_id=plan.id,
                code=item.code,
                name=item.name,
                in_plan=item.in_plan,
                credits=item.credits,
                hours_total=item.hours_total,
                hours_contact=item.hours_contact,
                hours_aud=item.hours_aud,
                hours_sr=item.hours_sr,
                hours_control=item.hours_control,
                department_code=item.department_code,
                plx_row_code=item.plx_row_code,
                nesting_level=item.nesting_level,
                row_order=item.row_order,
                object_type=item.object_type,
            )
            db.add(discipline)
            await db.flush()

            for comp_code in item.competencies:
                db.add(
                    PlanDisciplineCompetency(
                        id=uuid.uuid4(),
                        plan_discipline_id=discipline.id,
                        competency_code=comp_code,
                    )
                )

            for assessment in item.assessments:
                db.add(
                    PlanDisciplineAssessment(
                        id=uuid.uuid4(),
                        plan_discipline_id=discipline.id,
                        form_type=assessment.form_type,
                        semester=assessment.semester,
                        course=assessment.course,
                    )
                )

            db.add(
                Program(
                    id=uuid.uuid4(),
                    plan_discipline_id=discipline.id,
                    document_id=None,
                    status="missing",
                    program_kind=_program_kind_from_dto(item),
                )
            )


def _program_kind_from_dto(item: DisciplineDTO) -> str:
    bucket = classify_discipline_bucket(
        code=item.code,
        name=item.name,
        object_type=item.object_type,
    )
    if bucket == "gia":
        return "gia"
    if bucket == "practices":
        return "practice"
    return "discipline"
