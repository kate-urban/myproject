from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import plans_sync_on_nav
from app.models import Direction, PlanDiscipline, Profile, StudyPlan
from app.schemas import (
    BatchUploadOut,
    DisciplineValidationOut,
    FosDisciplineValidationOut,
    FosPlanValidationOut,
    PlanDisciplineOut,
    PlanValidationOut,
    StudyPlanImportOut,
    StudyPlanOut,
    ValidationRuleOut,
    ValidationWaiverIn,
)
from app.services.edit_lock import locks_for_program_ids
from app.services.importers import StudyPlanImporter
from app.services.document_upload import batch_ingest_documents
from app.services.plans_folder_nav import (
    build_plans_navigation_tree,
    import_plan_from_relative_path,
    resolve_plan_file_path,
)
from app.services.export_service import (
    build_export_summary,
    export_direction_year_package,
    export_plan_discipline,
    export_plan_discipline_pdf,
    export_plan_passed_zip,
)
from app.services.rpd_extractor import RpdExtract
from app.services.validation.section_texts import (
    document_ids_from_disciplines,
    load_section_texts_by_document,
)
from app.services.validation import (
    validate_program,
    validate_program_fos,
    validate_study_plan,
    validate_study_plan_fos,
)
from app.services.validation.waivers import (
    create_validation_waiver,
    delete_validation_waiver,
    load_waiver_rule_ids,
    load_waiver_rule_ids_by_program,
    resolve_discipline_program,
)
from app.api.auth_deps import get_current_user
from app.services.auth import CurrentUser
from app.utils.http_errors import public_error_message
from app.utils.upload_limits import read_upload_bytes
from app.services.validation.report_export import (
    build_validation_report_payload,
    payload_to_json,
    render_validation_report_html,
)
from app.utils.study_plan_filters import is_test_study_plan

router = APIRouter(prefix="/study-plans", tags=["study-plans"])

ALLOWED_EXTENSIONS = {".plx", ".xlsx", ".xlsm"}


async def _disciplines_count(db: AsyncSession, plan_id: UUID) -> int:
    counts = await _disciplines_counts(db, [plan_id])
    return counts.get(plan_id, 0)


async def _disciplines_counts(db: AsyncSession, plan_ids: list[UUID]) -> dict[UUID, int]:
    if not plan_ids:
        return {}
    rows = await db.execute(
        select(PlanDiscipline.study_plan_id, func.count())
        .where(PlanDiscipline.study_plan_id.in_(plan_ids))
        .group_by(PlanDiscipline.study_plan_id)
    )
    return {plan_id: int(count) for plan_id, count in rows.all()}


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
        waived=item.waived,
    )


def _program_ids_from_disciplines(disciplines: list[PlanDiscipline]) -> list[UUID]:
    return [
        discipline.program.id
        for discipline in disciplines
        if discipline.program is not None
    ]


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


@router.get("/navigation-tree/")
async def get_plans_navigation_tree(
    sync: bool = Query(False, description="Импортировать новые .plx/.xlsx из папки УП"),
    db: AsyncSession = Depends(get_db),
):
    """Дерево папки «УЧЕБНЫЕ ПЛАНЫ» с привязанными импортированными планами."""
    do_sync = sync or plans_sync_on_nav()
    return await build_plans_navigation_tree(db, sync=do_sync)


@router.post("/import-from-folder/", response_model=StudyPlanImportOut)
async def import_study_plan_from_folder(
    relative_path: str = Query(..., description="Путь к файлу от корня папки УП"),
    db: AsyncSession = Depends(get_db),
):
    try:
        resolve_plan_file_path(relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        plan = await import_plan_from_relative_path(db, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=public_error_message(
                exc,
                fallback="Не удалось импортировать учебный план",
            ),
        ) from exc

    return await _build_import_response(plan.id, db)


@router.post("/{plan_id}/batch-upload-docs/", response_model=BatchUploadOut)
async def batch_upload_plan_documents(
    plan_id: UUID,
    files: list[UploadFile] = File(...),
    propagate_all_plans: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Пакетная загрузка .doc/.docx из папки: конвертация .doc и привязка к дисциплинам УП."""
    plan = await _load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    if not files:
        raise HTTPException(status_code=400, detail="Не выбраны файлы")
    return await batch_ingest_documents(
        db,
        study_plan_id=plan_id,
        propagate_all_plans=propagate_all_plans,
        uploads=files,
    )


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
    filtered = [
        plan
        for plan in plans
        if not is_test_study_plan(plan, direction_code=plan.profile.direction.code)
    ]
    counts = await _disciplines_counts(db, [plan.id for plan in filtered])
    return [
        _plan_to_out(plan, plan.profile.direction, plan.profile, counts.get(plan.id, 0))
        for plan in filtered
    ]


@router.get("/export-package/")
async def export_direction_year_package_endpoint(
    direction_code: str = Query(..., min_length=1),
    year: int = Query(..., ge=2000, le=2100),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Пакетный ZIP по направлению и году набора (ТЗ P1)."""
    try:
        zip_path, meta = await export_direction_year_package(
            db,
            direction_code=direction_code,
            year=year,
            force=force,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"package_{direction_code}_{year}.zip",
        headers={"X-Exported-Count": str(meta.get("exported", 0))},
    )


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
    db: AsyncSession = Depends(get_db),
    code: Optional[str] = Query(default=None),
):
    plan = await db.get(StudyPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    stmt = (
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.competencies),
            selectinload(PlanDiscipline.assessments),
            selectinload(PlanDiscipline.program),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order, PlanDiscipline.code)
    )
    if code:
        stmt = stmt.where(PlanDiscipline.code == code)

    disciplines = (await db.execute(stmt)).scalars().all()
    program_ids = [d.program.id for d in disciplines if d.program]
    lock_map = await locks_for_program_ids(db, program_ids)
    return [_discipline_to_out(item, lock_map) for item in disciplines]


def _discipline_to_out(
    discipline: PlanDiscipline,
    lock_map: dict | None = None,
) -> PlanDisciplineOut:
    program = discipline.program
    lock = (lock_map or {}).get(program.id) if program else None
    rpd_extract: RpdExtract | None = None
    if program and program.rpd_extract_json:
        rpd_extract = RpdExtract.from_json(program.rpd_extract_json)
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
        rpd_approval_year=rpd_extract.approval_year if rpd_extract else None,
        rpd_has_reapproval_section=rpd_extract.has_reapproval_section if rpd_extract else False,
        rpd_reapproval_years=rpd_extract.reapproval_years if rpd_extract else [],
        rpd_authors=rpd_extract.authors if rpd_extract else [],
        passport_needs_manual=rpd_extract.passport_needs_manual if rpd_extract else False,
        program_id=program.id if program else None,
        lock_holder=lock.user_display_name if lock else None,
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
            selectinload(PlanDiscipline.assessments),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    parsed_rules = rule_ids.split() if rule_ids else None
    section_texts_by_document = await load_section_texts_by_document(
        db,
        document_ids_from_disciplines(disciplines),
    )
    waivers_by_program = await load_waiver_rule_ids_by_program(
        db, _program_ids_from_disciplines(disciplines), "rpd"
    )
    from app.services.rpd_extract_refresh import ensure_fresh_rpd_extract

    for discipline in disciplines:
        if discipline.program and discipline.program.document_id:
            await ensure_fresh_rpd_extract(db, discipline.program)
    report = validate_study_plan(
        plan,
        disciplines,
        rule_ids=parsed_rules,
        section_texts_by_document=section_texts_by_document,
        waivers_by_program_id=waivers_by_program,
    )

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
            selectinload(PlanDiscipline.assessments),
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
    all_disciplines = (
        await db.execute(
            select(PlanDiscipline)
            .options(selectinload(PlanDiscipline.program))
            .where(PlanDiscipline.study_plan_id == plan_id)
            .order_by(PlanDiscipline.row_order, PlanDiscipline.code)
        )
    ).scalars().all()
    section_texts_map = await load_section_texts_by_document(
        db,
        [discipline.program.document_id],
    )
    waived = await load_waiver_rule_ids(db, discipline.program.id, "rpd")
    from app.services.rpd_extract_refresh import ensure_fresh_rpd_extract

    await ensure_fresh_rpd_extract(db, discipline.program)
    try:
        report = validate_program(
            plan,
            discipline,
            discipline.program,
            rule_ids=parsed_rules,
            section_texts=section_texts_map.get(str(discipline.program.document_id)),
            plan_disciplines=list(all_disciplines),
            waived_rule_ids=waived,
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
            selectinload(PlanDiscipline.assessments),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    parsed_rules = rule_ids.split() if rule_ids else None
    waivers_by_program = await load_waiver_rule_ids_by_program(
        db, _program_ids_from_disciplines(disciplines), "fos"
    )
    report = validate_study_plan_fos(
        plan,
        disciplines,
        rule_ids=parsed_rules,
        waivers_by_program_id=waivers_by_program,
    )

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
            selectinload(PlanDiscipline.assessments),
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
    waived = await load_waiver_rule_ids(db, discipline.program.id, "fos")
    try:
        report = validate_program_fos(
            plan,
            discipline,
            discipline.program,
            rule_ids=parsed_rules,
            waived_rule_ids=waived,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _fos_report_to_out(report)


@router.post(
    "/{plan_id}/disciplines/{discipline_id}/validation-waivers/",
    response_model=Union[DisciplineValidationOut, FosDisciplineValidationOut],
)
async def create_plan_discipline_validation_waiver(
    plan_id: UUID,
    discipline_id: UUID,
    body: ValidationWaiverIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    try:
        discipline, program_id = await resolve_discipline_program(db, plan_id, discipline_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await create_validation_waiver(
        db,
        program_id=program_id,
        doc_kind=body.kind,
        rule_id=body.rule_id.strip().upper(),
        comment=body.comment,
        created_by=user.id,
    )
    await db.commit()

    if body.kind == "rpd":
        return await validate_plan_discipline(plan_id, discipline_id, rule_ids=None, db=db)
    return await validate_plan_discipline_fos(plan_id, discipline_id, rule_ids=None, db=db)


@router.delete(
    "/{plan_id}/disciplines/{discipline_id}/validation-waivers/{rule_id}/",
    response_model=Union[DisciplineValidationOut, FosDisciplineValidationOut],
)
async def delete_plan_discipline_validation_waiver(
    plan_id: UUID,
    discipline_id: UUID,
    rule_id: str,
    kind: str = Query(..., pattern="^(rpd|fos)$"),
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    try:
        _discipline, program_id = await resolve_discipline_program(db, plan_id, discipline_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    deleted = await delete_validation_waiver(
        db,
        program_id=program_id,
        doc_kind=kind,
        rule_id=rule_id.strip().upper(),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Снятие не найдено")
    await db.commit()

    if kind == "rpd":
        return await validate_plan_discipline(plan_id, discipline_id, rule_ids=None, db=db)
    return await validate_plan_discipline_fos(plan_id, discipline_id, rule_ids=None, db=db)


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
            selectinload(PlanDiscipline.assessments),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    disciplines = list(result.scalars().all())

    section_texts_by_document = await load_section_texts_by_document(
        db,
        document_ids_from_disciplines(disciplines),
    )
    program_ids = _program_ids_from_disciplines(disciplines)
    rpd_waivers = await load_waiver_rule_ids_by_program(db, program_ids, "rpd")
    fos_waivers = await load_waiver_rule_ids_by_program(db, program_ids, "fos")
    rpd_report = validate_study_plan(
        plan,
        disciplines,
        section_texts_by_document=section_texts_by_document,
        waivers_by_program_id=rpd_waivers,
    )
    fos_report = validate_study_plan_fos(
        plan,
        disciplines,
        waivers_by_program_id=fos_waivers,
    )
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


@router.get("/{plan_id}/export-summary/")
async def export_summary_endpoint(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    disciplines = await _load_disciplines_for_validation(db, plan_id)
    return await build_export_summary(db, plan, disciplines)


@router.get("/{plan_id}/disciplines/{discipline_id}/export/")
async def export_discipline_document(
    plan_id: UUID,
    discipline_id: UUID,
    kind: str = Query("rpd", pattern="^(rpd|fos)$"),
    template_id: Optional[str] = Query(None),
    force: bool = Query(False, description="Экспорт даже при ошибках сверки"),
    part: Optional[str] = Query(
        None,
        pattern="^(literature|zuv|po)$",
        description="Частичный экспорт: literature, zuv или po",
    ),
    export_mode: str = Query(
        "template",
        pattern="^(template|original)$",
        description="template — макет Layout/; original — инкрементально в загруженный DOCX",
    ),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    discipline = await _get_discipline(db, plan_id, discipline_id)
    try:
        output_path, stats, filename = await export_plan_discipline(
            db,
            plan=plan,
            discipline=discipline,
            doc_kind=kind,
            template_id=template_id,
            force=force,
            part=part,
            export_mode=export_mode,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
        headers={
            "X-Export-Mode": str(stats.get("mode", "")),
            "X-Sections-Injected": str(stats.get("injected", 0)),
        },
    )


@router.get("/{plan_id}/disciplines/{discipline_id}/export.pdf")
async def export_discipline_pdf(
    plan_id: UUID,
    discipline_id: UUID,
    kind: str = Query("rpd", pattern="^(rpd|fos)$"),
    template_id: Optional[str] = Query(None),
    force: bool = Query(False),
    part: Optional[str] = Query(None, pattern="^(literature|zuv|po)$"),
    export_mode: str = Query("template", pattern="^(template|original)$"),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    discipline = await _get_discipline(db, plan_id, discipline_id)
    try:
        output_path, stats, filename = await export_plan_discipline_pdf(
            db,
            plan=plan,
            discipline=discipline,
            doc_kind=kind,
            template_id=template_id,
            force=force,
            part=part,
            export_mode=export_mode,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=filename,
        headers={"X-Export-Mode": str(stats.get("mode", ""))},
    )


@router.get("/{plan_id}/export-passed/")
async def export_plan_passed_documents(
    plan_id: UUID,
    kind: str = Query("rpd", pattern="^(rpd|fos)$"),
    template_id: Optional[str] = Query(None),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    plan = await _load_plan_for_validation(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    disciplines = await _load_disciplines_for_validation(db, plan_id)
    try:
        zip_path, meta = await export_plan_passed_zip(
            db,
            plan=plan,
            disciplines=disciplines,
            doc_kind=kind,
            template_id=template_id,
            force=force,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"export_{kind}_{plan_id}.zip",
        headers={"X-Exported-Count": str(meta.get("exported", 0))},
    )


async def _load_disciplines_for_validation(db: AsyncSession, plan_id: UUID) -> list[PlanDiscipline]:
    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
            selectinload(PlanDiscipline.assessments),
        )
        .where(PlanDiscipline.study_plan_id == plan_id)
        .order_by(PlanDiscipline.row_order)
    )
    return list(result.scalars().all())


async def _get_discipline(
    db: AsyncSession,
    plan_id: UUID,
    discipline_id: UUID,
) -> PlanDiscipline:
    result = await db.execute(
        select(PlanDiscipline)
        .options(
            selectinload(PlanDiscipline.program),
            selectinload(PlanDiscipline.competencies),
            selectinload(PlanDiscipline.assessments),
        )
        .where(
            PlanDiscipline.study_plan_id == plan_id,
            PlanDiscipline.id == discipline_id,
        )
    )
    discipline = result.scalar_one_or_none()
    if discipline is None:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    return discipline


@router.post("/import/", response_model=StudyPlanImportOut)
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

    content = await read_upload_bytes(file)
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
            detail=public_error_message(
                exc,
                fallback="Не удалось импортировать учебный план",
            ),
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
