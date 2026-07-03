"""Запись StudyPlanDTO в PostgreSQL."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Direction,
    PlanDiscipline,
    PlanDisciplineCompetency,
    Profile,
    Program,
    StudyPlan,
)
from app.services.importers.dto import StudyPlanDTO
from app.services.importers.plx_excel import PlxExcelReader
from app.services.importers.plx_xml import PlxXmlReader


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
    ) -> StudyPlan:
        if db is None:
            raise ValueError("db session is required")
        dto = self.read_dto(path, content=content, filename=filename)
        return await self.import_dto(dto, db)

    async def import_dto(self, dto: StudyPlanDTO, db: AsyncSession) -> StudyPlan:
        direction = await self._get_or_create_direction(db, dto)
        profile = await self._get_or_create_profile(db, direction, dto)
        plan = await self._upsert_study_plan(db, profile, dto)
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
        self, db: AsyncSession, profile: Profile, dto: StudyPlanDTO
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
                form=dto.form,
                year=dto.year,
                qualification=dto.qualification,
                fgos_number=dto.fgos_number,
            )
            db.add(plan)
        else:
            plan.source_file = dto.source_file
            plan.source_format = dto.source_format
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

        for item in dto.disciplines:
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

            db.add(
                Program(
                    id=uuid.uuid4(),
                    plan_discipline_id=discipline.id,
                    document_id=None,
                    status="missing",
                )
            )
