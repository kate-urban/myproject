from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Direction, PlanDiscipline, Profile, StudyPlan
from app.schemas import (
    DisciplineValidationOut,
    FosDisciplineValidationOut,
    FosPlanValidationOut,
    PlanDisciplineOut,
    PlanValidationOut,
    StudyPlanImportOut,
    StudyPlanOut,
    ValidationRuleOut,
)
from app.services.importers import StudyPlanImporter
from app.services.validation import (
    validate_program,
    validate_program_fos,
    validate_study_plan,
    validate_study_plan_fos,
)
from app.services.validation.report_export import (
    build_validation_report_payload,
    payload_to_json,
    render_validation_report_html,
)

router = APIRouter(prefix="/study-plans", tags=["study-plans"])

ALLOWED_EXTENSIONS = {".plx", ".xlsx", ".xlsm"}


async def _disciplines_count(db: AsyncSession, plan_id: UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(PlanDiscipline)
        .where(PlanDiscipline.study_plan_id == plan_id)
    )
    return count or 0


def _plan_to_out(plan: StudyPlan, direction: Direction, profile: Profile, count: int) -> StudyPlanOut:
    return StudyPlanOut(
        id=plan.id,
        source_file=plan.source_file,
        source_format=plan.source_format,
        direction_code=direction.code,
        direction_name=direction.name,
        profile_name=profile.name,
        form=plan.form,
        year=plan.year,
        disciplines_count=count,
        imported_at=plan.imported_at,
    )


async def _load_plan_for_validation(db: AsyncSession, plan_id: UUID) -> StudyPlan | None:
    result = await db.execute(
        select(StudyPlan)
        .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
        .where(StudyPlan.id == plan_id)
    )
    return result.scalar_one_or_none()


def _rule_to_out(item) -> ValidationRuleOut:
    return ValidationRuleOut(
        rule_id=item.rule_id,
        name=item.name,
        passed=item.passed,
        message=item.message,
        expected=item.expected,
        actual=item.actual,
        skipped=item.skipped,
        severity=item.severity,
    )


def _discipline_report_to_out(report) -> DisciplineValidationOut:
    return DisciplineValidationOut(
        discipline_id=report.discipline_id,
        discipline_code=report.discipline_code,
        document_id=report.document_id,
        passed=report.passed,
        skipped=report.skipped,
        reason=report.reason,
        results=[_rule_to_out(item) for item in report.results],
    )


async def _load_plan(db: AsyncSession, plan_id: UUID) -> StudyPlan | None:
    return await _load_plan_for_validation(db, plan_id)


@router.get("/", response_model=list[StudyPlanOut])
async def list_study_plans(
    direction_code: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    form: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(StudyPlan)
        .join(Profile, StudyPlan.profile_id == Profile.id)
        .join(Direction, Profile.direction_id == Direction.id)
        .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
        .order_by(StudyPlan.imported_at.desc())
    )
    if direction_code:
        stmt = stmt.where(Direction.code == direction_code)
    if year is not None:
        stmt = stmt.where(StudyPlan.year == year)
    if form:
        stmt = stmt.where(StudyPlan.form == form)

    plans = (await db.execute(stmt)).scalars().all()
    result: list[StudyPlanOut] = []
    for plan in plans:
        count = await _disciplines_count(db, plan.id)
        result.append(
            _plan_to_out(plan, plan.profile.direction, plan.profile, count)
        )
    return result


@router.get("/{plan_id}/", response_model=StudyPlanOut)
async def get_study_plan(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    plan = await _load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    count = await _disciplines_count(db, plan.id)
    return _plan_to_out(plan, plan.profile.direction, plan.profile, count)


@router.get("/{plan_id}/disciplines/", response_model=list[PlanDisciplineOut])
async def list_plan_disciplines(
    plan_id: UUID,
    code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(StudyPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    stmt = (
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.competencies),
            selectinload(PlanDiscipline.program),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order, PlanDiscipline.code)
    )
    if code:
        stmt = stmt.where(PlanDiscipline.code == code)

    disciplines = (await db.execute(stmt)).scalars().all()
    return [_discipline_to_out(item) for item in disciplines]


def _discipline_to_out(discipline: PlanDiscipline) -> PlanDisciplineOut:
    program = discipline.program
    return PlanDisciplineOut(
        id=discipline.id,
        code=discipline.code,
        name=discipline.name,
        in_plan=discipline.in_plan,
        credits=discipline.credits,
        hours_total=discipline.hours_total,
        hours_contact=discipline.hours_contact,
        hours_aud=discipline.hours_aud,
        hours_sr=discipline.hours_sr,
        hours_control=discipline.hours_control,
        department_code=discipline.department_code,
        competencies=[c.competency_code for c in discipline.competencies],
        program_status=program.status if program else None,
        document_id=program.document_id if program else None,
        fos_document_id=program.fos_document_id if program else None,
    )


@router.get(
    "/{plan_id}/validate/",
    response_model=PlanValidationOut,
)
async def validate_study_plan_endpoint(
    plan_id: UUID,
    rule_ids: Optional[str] = Query(
        None,
        description="Пробел-разделённый список правил, например: R001 R020",
    ),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    parsed_rules = rule_ids.split() if rule_ids else None
    report = validate_study_plan(plan, disciplines, rule_ids=parsed_rules)

    return PlanValidationOut(
        study_plan_id=report.study_plan_id,
        total_disciplines=report.total_disciplines,
        checked=report.checked,
        passed=report.passed,
        failed=report.failed,
        missing_rpd=report.missing_rpd,
        passed_all=report.passed_all,
        items=[_discipline_report_to_out(item) for item in report.items],
    )


@router.get(
    "/{plan_id}/disciplines/{discipline_id}/validate/",
    response_model=DisciplineValidationOut,
)
async def validate_plan_discipline(
    plan_id: UUID,
    discipline_id: UUID,
    rule_ids: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
        )
        .where(
            PlanDiscipline.id == discipline_id,
            PlanDiscipline.study_plan_id == plan_id,
        )
    )
    discipline = result.scalar_one_or_none()
    if discipline is None:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена в этом учебном плане")

    if discipline.program is None:
        raise HTTPException(status_code=422, detail="РПД не привязана к дисциплине")

    parsed_rules = rule_ids.split() if rule_ids else None
    try:
        report = validate_program(
            plan,
            discipline,
            discipline.program,
            rule_ids=parsed_rules,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _discipline_report_to_out(report)


def _fos_report_to_out(report) -> FosDisciplineValidationOut:
    from uuid import UUID

    def _as_uuid(value: str | None):
        if value is None:
            return None
        return UUID(value)

    return FosDisciplineValidationOut(
        discipline_id=report.discipline_id,
        discipline_code=report.discipline_code,
        rpd_document_id=_as_uuid(report.rpd_document_id),
        fos_document_id=_as_uuid(report.fos_document_id),
        passed=report.passed,
        skipped=report.skipped,
        reason=report.reason,
        results=[_rule_to_out(item) for item in report.results],
    )


@router.get(
    "/{plan_id}/validate-fos/",
    response_model=FosPlanValidationOut,
)
async def validate_study_plan_fos_endpoint(
    plan_id: UUID,
    rule_ids: Optional[str] = Query(
        None,
        description="Пробел-разделённый список правил, например: F001 F006",
    ),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    parsed_rules = rule_ids.split() if rule_ids else None
    report = validate_study_plan_fos(plan, disciplines, rule_ids=parsed_rules)

    return FosPlanValidationOut(
        study_plan_id=report.study_plan_id,
        total_disciplines=report.total_disciplines,
        checked=report.checked,
        passed=report.passed,
        failed=report.failed,
        missing_fos=report.missing_fos,
        fos_only=report.fos_only,
        passed_all=report.passed_all,
        items=[_fos_report_to_out(item) for item in report.items],
    )


@router.get(
    "/{plan_id}/disciplines/{discipline_id}/validate-fos/",
    response_model=FosDisciplineValidationOut,
)
async def validate_plan_discipline_fos(
    plan_id: UUID,
    discipline_id: UUID,
    rule_ids: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
        )
        .where(
            PlanDiscipline.id == discipline_id,
            PlanDiscipline.study_plan_id == plan_id,
        )
    )
    discipline = result.scalar_one_or_none()
    if discipline is None:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена в этом учебном плане")

    if discipline.program is None or discipline.program.fos_document_id is None:
        raise HTTPException(status_code=422, detail="ФОС не привязана к дисциплине")

    parsed_rules = rule_ids.split() if rule_ids else None
    try:
        report = validate_program_fos(
            plan,
            discipline,
            discipline.program,
            rule_ids=parsed_rules,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _fos_report_to_out(report)


@router.get("/{plan_id}/validation-report/")
async def export_validation_report(
    plan_id: UUID,
    format: str = Query("json", pattern="^(json|html)$"),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    rpd_report = validate_study_plan(plan, disciplines)
    fos_report = validate_study_plan_fos(plan, disciplines)
    payload = build_validation_report_payload(
        plan,
        rpd_report=rpd_report,
        fos_report=fos_report,
    )

    if format == "html":
        content = render_validation_report_html(payload)
        filename = f"validation_{plan_id}.html"
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return Response(
        content=payload_to_json(payload),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="validation_{plan_id}.json"'},
    )


@router.post("/import", response_model=StudyPlanImportOut)
async def import_study_plan(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются файлы .plx, .xlsx, .xlsm",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")

    importer = StudyPlanImporter()
    try:
        plan = await importer.import_file(
            content=content,
            filename=filename,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Не удалось импортировать учебный план: {exc}",
        ) from exc

    return await _build_import_response(plan.id, db)


async def _build_import_response(plan_id: UUID, db: AsyncSession) -> StudyPlanImportOut:
    plan = await _load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    count = await _disciplines_count(db, plan.id)
    profile = plan.profile
    direction = profile.direction

    return StudyPlanImportOut(
        id=plan.id,
        source_file=plan.source_file,
        source_format=plan.source_format,
        direction_code=direction.code,
        direction_name=direction.name,
        profile_name=profile.name,
        form=plan.form,
        year=plan.year,
        disciplines_count=count,
        imported_at=plan.imported_at,
    )
