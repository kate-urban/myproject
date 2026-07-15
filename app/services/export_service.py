"""Экспорт DOCX после сверки: одна дисциплина или ZIP по плану."""

from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import (
    AUTO_SYNC_USER_TEMPLATE,
    DEFAULT_FOS_TEMPLATE_ID,
    DEFAULT_FOS_TEMPLATE_NAME,
    DEFAULT_RPD_TEMPLATE_ID,
    DEFAULT_RPD_TEMPLATE_NAME,
    EXPORT_REQUIRE_REAPPROVAL,
    EXPORT_REQUIRE_VALIDATION,
    EXPORT_USE_ORIGINAL,
    export_batch_max_parallel,
)
from app.database import AsyncSessionLocal
from app.models import Document, ExportJob, PlanDiscipline, Profile, Program, Section, StudyPlan, Template
from app.services.document_storage import resolve_document_source_path
from app.services.editable_template_sync import sync_user_template_for_export
from app.services.export_cleanup import cleanup_exports_directory
from app.services.export_finalize import finalize_export_docx
from app.services.export_tagged_template import render_tagged_template, template_uses_tagged_layout
from app.services.exporter import Exporter
from app.services.rpd_extractor import RpdExtract
from app.services.template_manager import get_template_path, seed_layout_templates
from app.services.validation import validate_program, validate_program_fos
from app.services.validation.section_texts import load_section_texts_by_document
from app.services.validation.waivers import load_waiver_rule_ids, load_waiver_rule_ids_by_program
from app.services.validation.fos_engine import _is_passed as fos_is_passed
from app.services.validation.engine import _is_passed as rpd_is_passed

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORTS_DIR = os.getenv("EXPORTS_DIR", str(_PROJECT_ROOT / "exports"))
os.makedirs(EXPORTS_DIR, exist_ok=True)

_SAFE_CODE_RE = re.compile(r"[^\w\-.]+", re.UNICODE)


def _safe_filename(code: str, name: str, suffix: str) -> str:
    code_part = _SAFE_CODE_RE.sub("_", code).strip("_") or "discipline"
    name_part = _SAFE_CODE_RE.sub("_", name)[:40].strip("_")
    return f"{code_part}_{name_part}_{suffix}.docx"


async def resolve_template_id(
    db: AsyncSession,
    *,
    doc_kind: str,
    template_id: str | None = None,
) -> str:
    if template_id:
        return template_id

    env_id = DEFAULT_RPD_TEMPLATE_ID if doc_kind == "rpd" else DEFAULT_FOS_TEMPLATE_ID
    if env_id:
        return env_id

    await seed_layout_templates()
    preferred = DEFAULT_RPD_TEMPLATE_NAME if doc_kind == "rpd" else DEFAULT_FOS_TEMPLATE_NAME
    result = await db.execute(select(Template).order_by(Template.name))
    templates = list(result.scalars().all())
    for item in templates:
        if preferred.lower() in item.name.lower():
            return str(item.id)
    keyword = "РПД" if doc_kind == "rpd" else "ФОС"
    for item in templates:
        if keyword in item.name.upper():
            return str(item.id)
    if not templates:
        raise ValueError("Шаблоны не найдены — положите макет в Layout/ и перезапустите сервер")
    return str(templates[0].id)


def _check_reapproval_ready(rpd: RpdExtract | None) -> tuple[bool, str | None]:
    if not EXPORT_REQUIRE_REAPPROVAL:
        return True, None
    if rpd is None:
        return False, "Нет метаданных РПД для проверки переутверждения"
    if rpd.reapproval_years:
        return True, None
    if rpd.has_reapproval_section:
        return False, "Раздел переутверждения есть, но годы не заполнены"
    return False, "Нет листа переутверждения — заполните в документе или настройте REAPPROVAL_CURRENT_YEAR"


PARTIAL_EXPORT_PARTS: dict[str, tuple[str, ...]] = {
    "literature": ("литератур", "библиограф", "источник"),
    "zuv": ("зув", "знать", "уметь", "владеть", "компетенц"),
    "po": ("программ", "обеспеч", "материальн", "мто"),
}


def _filter_sections_for_part(sections: list[Section], part: str | None) -> list[Section]:
    if not part:
        return sections
    keys = PARTIAL_EXPORT_PARTS.get(part)
    if keys is None:
        raise ValueError(f"Неизвестная часть экспорта: {part}")
    filtered = [s for s in sections if any(k in s.section_name.lower() for k in keys)]
    if not filtered:
        raise ValueError(f"Разделы для части «{part}» не найдены")
    return filtered


async def _load_sections(
    db: AsyncSession,
    document_id: UUID,
    *,
    part: str | None = None,
) -> tuple[Document, list[Section]]:
    doc_result = await db.execute(select(Document).where(Document.id == document_id))
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise ValueError("Документ не найден")

    sec_result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    )
    sections = list(sec_result.scalars().all())
    sections = _filter_sections_for_part(sections, part)
    if not sections:
        raise ValueError("Разделы документа не найдены")
    return document, sections


async def export_document_core(
    db: AsyncSession,
    *,
    document_id: UUID,
    template_id: str,
    doc_kind: str,
    discipline_code: str | None = None,
    discipline_name: str | None = None,
    rpd: RpdExtract | None = None,
    download_name: str | None = None,
    study_plan_id: UUID | None = None,
    plan_discipline_id: UUID | None = None,
    validation_passed: bool | None = None,
    part: str | None = None,
    export_mode: str = "template",
) -> tuple[str, dict, str]:
    document, sections = await _load_sections(db, document_id, part=part)
    sections_dict = {
        s.section_name: s.content
        for s in sections
        if s.content and str(s.content).strip()
    }
    sections_order = [s.section_name for s in sections]

    template_result = await db.execute(select(Template).where(Template.id == template_id))
    template = template_result.scalar_one_or_none()
    template_name = template.name if template else None

    source_file = None
    use_original = export_mode == "original" or (
        export_mode != "template" and EXPORT_USE_ORIGINAL
    )
    if use_original:
        source_file = resolve_document_source_path(document.id, source_path=document.source_path)
    elif AUTO_SYNC_USER_TEMPLATE and export_mode == "template":
        sync_user_template_for_export(doc_kind)

    template_path = await get_template_path(template_id)
    use_tagged_template = (
        not use_original
        and export_mode == "template"
        and template_path
        and template_uses_tagged_layout(template_path)
    )

    output_path = os.path.join(EXPORTS_DIR, f"{document_id}.docx")

    if use_tagged_template:
        from app.services.department_lookup import department_names_by_codes
        from app.services.pdf_export import load_active_signatures

        signatures = await load_active_signatures(db) if doc_kind == "rpd" else []
        department_name = None
        direction_code = None
        direction_name = None
        profile_name = None

        if study_plan_id and plan_discipline_id:
            plan_row = await db.execute(
                select(StudyPlan)
                .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
                .where(StudyPlan.id == study_plan_id)
            )
            plan_obj = plan_row.scalar_one_or_none()
            disc_row = await db.execute(
                select(PlanDiscipline).where(PlanDiscipline.id == plan_discipline_id)
            )
            disc_obj = disc_row.scalar_one_or_none()
            if plan_obj and plan_obj.profile:
                profile_name = plan_obj.profile.name
                if plan_obj.profile.direction:
                    direction_code = plan_obj.profile.direction.code
                    direction_name = plan_obj.profile.direction.name
            if disc_obj and disc_obj.department_code:
                names = await department_names_by_codes(
                    db,
                    {disc_obj.department_code},
                    enrollment_year=plan_obj.year if plan_obj else None,
                )
                department_name = names.get(disc_obj.department_code)

        tagged_stats = await asyncio.to_thread(
            render_tagged_template,
            template_path=template_path,
            output_path=output_path,
            sections_data=sections_dict,
            sections_order=sections_order,
            project_root=_PROJECT_ROOT,
            rpd=rpd,
            discipline_code=discipline_code,
            discipline_name=discipline_name,
            direction_code=direction_code,
            direction_name=direction_name,
            profile_name=profile_name,
            department_name=department_name,
            authors=list(rpd.authors) if rpd and rpd.authors else None,
            signatures=signatures,
        )
        stats = {
            "mode": "tagged",
            "sections_total": len(sections_order),
            **tagged_stats,
        }
    else:
        output_path, stats = await Exporter.export_document(
            document_id=str(document_id),
            sections_data=sections_dict,
            template_id=template_id,
            output_dir=EXPORTS_DIR,
            sections_order=sections_order,
            doc_type=doc_kind if doc_kind == "fos" else document.doc_type,
            template_name=template_name,
            source_path=str(source_file) if source_file else None,
            incremental=use_original,
        )

    finalize_stats = {}
    if doc_kind == "rpd":
        from app.services.department_lookup import department_names_by_codes
        from app.services.pdf_export import load_active_signatures

        signatures = await load_active_signatures(db)
        department_name = None
        direction_code = None
        direction_name = None
        profile_name = None
        credits = None
        assessments = None

        if study_plan_id and plan_discipline_id:
            plan_row = await db.execute(
                select(StudyPlan)
                .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
                .where(StudyPlan.id == study_plan_id)
            )
            plan_obj = plan_row.scalar_one_or_none()
            disc_row = await db.execute(
                select(PlanDiscipline)
                .options(selectinload(PlanDiscipline.assessments))
                .where(PlanDiscipline.id == plan_discipline_id)
            )
            disc_obj = disc_row.scalar_one_or_none()
            if plan_obj and plan_obj.profile:
                profile_name = plan_obj.profile.name
                if plan_obj.profile.direction:
                    direction_code = plan_obj.profile.direction.code
                    direction_name = plan_obj.profile.direction.name
            if disc_obj:
                credits = disc_obj.credits
                assessments = list(disc_obj.assessments or [])
                if disc_obj.department_code:
                    names = await department_names_by_codes(
                        db, {disc_obj.department_code}, enrollment_year=plan_obj.year if plan_obj else None
                    )
                    department_name = names.get(disc_obj.department_code)

        finalize_stats = finalize_export_docx(
            output_path,
            rpd=rpd,
            discipline_code=discipline_code,
            discipline_name=discipline_name,
            direction_code=direction_code,
            direction_name=direction_name,
            profile_name=profile_name,
            department_name=department_name,
            credits=credits,
            assessments=assessments,
            authors=list(rpd.authors) if rpd and rpd.authors else None,
            signatures=signatures,
            tagged_template=use_tagged_template,
        )
    elif use_tagged_template:
        finalize_stats = finalize_export_docx(
            output_path,
            tagged_template=True,
            fill_signatures=False,
            fill_reapproval=False,
        )
    stats.update(finalize_stats)

    filename = download_name or f"document_{document_id}.docx"

    job = ExportJob(
        id=uuid.uuid4(),
        study_plan_id=study_plan_id,
        plan_discipline_id=plan_discipline_id,
        document_id=document_id,
        doc_kind=doc_kind,
        output_filename=filename,
        validation_passed=validation_passed,
        export_mode=str(stats.get("mode", "")),
    )
    db.add(job)
    await db.flush()

    return output_path, stats, filename


async def export_plan_discipline(
    db: AsyncSession,
    *,
    plan: StudyPlan,
    discipline: PlanDiscipline,
    doc_kind: str = "rpd",
    template_id: str | None = None,
    force: bool = False,
    part: str | None = None,
    export_mode: str = "template",
) -> tuple[str, dict, str]:
    program = discipline.program
    if program is None:
        raise ValueError("Программа не найдена для дисциплины")

    document_id = program.document_id if doc_kind == "rpd" else program.fos_document_id
    if document_id is None:
        raise ValueError("Документ не загружен")

    validation_passed = True
    rpd: RpdExtract | None = None

    if doc_kind == "rpd":
        section_texts_map = await load_section_texts_by_document(db, [document_id])
        waived = await load_waiver_rule_ids(db, program.id, "rpd")
        report = validate_program(
            plan,
            discipline,
            program,
            section_texts=section_texts_map.get(str(document_id)),
            waived_rule_ids=waived,
        )
        validation_passed = rpd_is_passed(report.results)
        if EXPORT_REQUIRE_VALIDATION and not force and not validation_passed:
            failed = [r for r in report.results if not r.skipped and r.severity == "critical" and not r.passed]
            rules = ", ".join(r.rule_id for r in failed[:6])
            raise ValueError(f"Сверка РПД не пройдена ({rules})")
        rpd = RpdExtract.from_json(program.rpd_extract_json) if program.rpd_extract_json else None
        ok, msg = _check_reapproval_ready(rpd)
        if EXPORT_REQUIRE_REAPPROVAL and not force and not ok:
            raise ValueError(msg or "Переутверждение не заполнено")
    else:
        waived = await load_waiver_rule_ids(db, program.id, "fos")
        report = validate_program_fos(
            plan, discipline, program, waived_rule_ids=waived
        )
        validation_passed = fos_is_passed(report.results)
        if EXPORT_REQUIRE_VALIDATION and not force and not validation_passed:
            failed = [r for r in report.results if not r.skipped and r.severity == "critical" and not r.passed]
            rules = ", ".join(r.rule_id for r in failed[:6])
            raise ValueError(f"Сверка ФОС не пройдена ({rules})")

    resolved_template = await resolve_template_id(db, doc_kind=doc_kind, template_id=template_id)
    suffix = "RPD" if doc_kind == "rpd" else "FOS"
    filename = _safe_filename(discipline.code, discipline.name, suffix)

    return await export_document_core(
        db,
        document_id=document_id,
        template_id=resolved_template,
        doc_kind=doc_kind,
        discipline_code=discipline.code,
        discipline_name=discipline.name,
        rpd=rpd,
        download_name=filename,
        study_plan_id=plan.id,
        plan_discipline_id=discipline.id,
        validation_passed=validation_passed,
        part=part,
        export_mode=export_mode,
    )


async def export_plan_discipline_pdf(
    db: AsyncSession,
    *,
    plan: StudyPlan,
    discipline: PlanDiscipline,
    doc_kind: str = "rpd",
    template_id: str | None = None,
    force: bool = False,
    part: str | None = None,
    export_mode: str = "template",
) -> tuple[str, dict, str]:
    from app.services.pdf_export import finalize_pdf_export

    docx_path, stats, docx_name = await export_plan_discipline(
        db,
        plan=plan,
        discipline=discipline,
        doc_kind=doc_kind,
        template_id=template_id,
        force=force,
        part=part,
        export_mode=export_mode,
    )
    program = discipline.program
    if program is None:
        raise ValueError("Программа не найдена")
    document_id = program.document_id if doc_kind == "rpd" else program.fos_document_id
    _, sections = await _load_sections(db, document_id, part=part)
    section_pairs = [(s.section_name, s.content or "") for s in sections]
    title = f"{discipline.code} — {discipline.name}"
    stem = Path(docx_name).stem
    pdf_path, pdf_name = await finalize_pdf_export(
        db,
        docx_path=docx_path,
        sections=section_pairs,
        title=title,
        download_stem=stem,
        exports_dir=EXPORTS_DIR,
    )
    cleanup_exports_directory(EXPORTS_DIR)
    return pdf_path, stats, pdf_name


async def export_plan_passed_zip(
    db: AsyncSession,
    *,
    plan: StudyPlan,
    disciplines: list[PlanDiscipline],
    doc_kind: str = "rpd",
    template_id: str | None = None,
    force: bool = False,
) -> tuple[str, dict]:
    exported: list[tuple[str, str]] = []
    skipped: list[dict] = []
    errors: list[dict] = []

    section_texts_by_document = {}
    waivers_by_program: dict[str, set[str]] = {}
    program_ids = [
        discipline.program.id
        for discipline in disciplines
        if discipline.program is not None
    ]
    if doc_kind == "rpd":
        doc_ids = [
            discipline.program.document_id
            for discipline in disciplines
            if discipline.program and discipline.program.document_id
        ]
        section_texts_by_document = await load_section_texts_by_document(db, doc_ids)
        waivers_by_program = await load_waiver_rule_ids_by_program(db, program_ids, "rpd")
    else:
        waivers_by_program = await load_waiver_rule_ids_by_program(db, program_ids, "fos")

    for discipline in disciplines:
        program = discipline.program
        if program is None:
            skipped.append({"code": discipline.code, "reason": "no_program"})
            continue
        doc_id = program.document_id if doc_kind == "rpd" else program.fos_document_id
        if doc_id is None:
            skipped.append({"code": discipline.code, "reason": "no_document"})
            continue
        try:
            if doc_kind == "rpd":
                report = validate_program(
                    plan,
                    discipline,
                    program,
                    section_texts=section_texts_by_document.get(str(doc_id)),
                    waived_rule_ids=waivers_by_program.get(str(program.id)),
                )
                passed = rpd_is_passed(report.results)
            else:
                report = validate_program_fos(
                    plan,
                    discipline,
                    program,
                    waived_rule_ids=waivers_by_program.get(str(program.id)),
                )
                passed = fos_is_passed(report.results)
            if EXPORT_REQUIRE_VALIDATION and not force and not passed:
                skipped.append({"code": discipline.code, "reason": "validation_failed"})
                continue
            path, _stats, name = await export_plan_discipline(
                db,
                plan=plan,
                discipline=discipline,
                doc_kind=doc_kind,
                template_id=template_id,
                force=force,
            )
            exported.append((name, path))
        except ValueError as exc:
            errors.append({"code": discipline.code, "error": str(exc)})
        except Exception as exc:
            errors.append({"code": discipline.code, "error": str(exc)})

    if not exported:
        detail = errors[0]["error"] if errors else "Нет документов, прошедших сверку"
        raise ValueError(detail)

    zip_name = f"export_{plan.id}_{doc_kind}.zip"
    zip_path = os.path.join(EXPORTS_DIR, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in exported:
            zf.write(path, arcname=arcname)
        manifest = io.StringIO()
        manifest.write(f"exported={len(exported)}\n")
        for item in skipped:
            manifest.write(f"skipped={item['code']}:{item['reason']}\n")
        for item in errors:
            manifest.write(f"error={item['code']}:{item['error']}\n")
        zf.writestr("_manifest.txt", manifest.getvalue())

    cleanup_exports_directory(EXPORTS_DIR)
    return zip_path, {
        "exported": len(exported),
        "skipped": len(skipped),
        "errors": len(errors),
        "files": [name for name, _ in exported],
    }


async def build_export_summary(
    db: AsyncSession,
    plan: StudyPlan,
    disciplines: list[PlanDiscipline],
) -> dict:
    rpd_ready = 0
    fos_ready = 0
    rpd_passed = 0
    fos_passed = 0

    rpd_doc_ids = [
        discipline.program.document_id
        for discipline in disciplines
        if discipline.program and discipline.program.document_id
    ]
    section_texts_by_document = await load_section_texts_by_document(db, rpd_doc_ids)
    program_ids = [
        discipline.program.id
        for discipline in disciplines
        if discipline.program is not None
    ]
    rpd_waivers = await load_waiver_rule_ids_by_program(db, program_ids, "rpd")
    fos_waivers = await load_waiver_rule_ids_by_program(db, program_ids, "fos")

    for discipline in disciplines:
        program = discipline.program
        if program is None:
            continue
        if program.document_id:
            rpd_ready += 1
            try:
                report = validate_program(
                    plan,
                    discipline,
                    program,
                    section_texts=section_texts_by_document.get(str(program.document_id)),
                    waived_rule_ids=rpd_waivers.get(str(program.id)),
                )
                if rpd_is_passed(report.results):
                    rpd_passed += 1
            except ValueError:
                pass
        if program.fos_document_id:
            fos_ready += 1
            try:
                report = validate_program_fos(
                    plan,
                    discipline,
                    program,
                    waived_rule_ids=fos_waivers.get(str(program.id)),
                )
                if fos_is_passed(report.results):
                    fos_passed += 1
            except ValueError:
                pass

    return {
        "rpd_ready": rpd_ready,
        "rpd_passed": rpd_passed,
        "fos_ready": fos_ready,
        "fos_passed": fos_passed,
        "export_require_validation": EXPORT_REQUIRE_VALIDATION,
    }


@dataclass
class _PackageFile:
    arcname: str
    content: bytes | None = None
    path: str | None = None


@dataclass
class _PackageDisciplineResult:
    exported: int = 0
    skipped: int = 0
    manifest_items: list[dict] = field(default_factory=list)
    files: list[_PackageFile] = field(default_factory=list)


async def _export_package_discipline(
    *,
    plan_id: UUID,
    discipline_id: UUID,
    force: bool,
    package_signature,
) -> _PackageDisciplineResult:
    """Экспорт одной дисциплины для ZIP-пакета (отдельная сессия БД)."""
    from app.services.department_lookup import department_names_by_codes
    from app.services.reapproval_export import build_reapproval_pdf_bytes
    from app.utils.discipline_bucket import classify_discipline_bucket

    result = _PackageDisciplineResult()

    async with AsyncSessionLocal() as session:
        plan = await session.get(StudyPlan, plan_id)
        if plan is None:
            result.skipped += 1
            result.manifest_items.append({"status": "skipped", "reason": "no_plan"})
            return result

        disc_result = await session.execute(
            select(PlanDiscipline)
            .options(selectinload(PlanDiscipline.program).selectinload(Program.amendments))
            .where(
                PlanDiscipline.id == discipline_id,
                PlanDiscipline.study_plan_id == plan_id,
            )
        )
        discipline = disc_result.scalar_one_or_none()
        if discipline is None:
            result.skipped += 1
            result.manifest_items.append({"status": "skipped", "reason": "no_discipline"})
            return result

        program = discipline.program
        if program is None:
            result.skipped += 1
            result.manifest_items.append(
                {"code": discipline.code, "status": "skipped", "reason": "no_program"}
            )
            return result

        bucket = classify_discipline_bucket(
            code=discipline.code,
            name=discipline.name,
            object_type=getattr(discipline, "object_type", None),
        )
        folder = {"disciplines": "RPD", "practices": "RPP", "gia": "GIA"}.get(bucket, "RPD")
        rpd_exported = False

        if bucket == "practices" and program.constructor_json:
            from app.services.constructor_export import build_constructor_pdf_bytes_async

            try:
                pdf_data = await build_constructor_pdf_bytes_async(session, program, discipline)
                result.files.append(
                    _PackageFile(arcname=f"{folder}/{discipline.code}.pdf", content=pdf_data)
                )
                result.exported += 1
                rpd_exported = True
                result.manifest_items.append(
                    {"code": discipline.code, "status": "exported", "kind": "RPP"}
                )
            except ValueError as exc:
                result.skipped += 1
                result.manifest_items.append(
                    {"code": discipline.code, "status": "skipped", "reason": str(exc)}
                )
        elif program.document_id and bucket != "gia":
            try:
                path, _stats, name = await export_plan_discipline(
                    session,
                    plan=plan,
                    discipline=discipline,
                    doc_kind="rpd",
                    force=force,
                )
                result.files.append(_PackageFile(arcname=f"{folder}/{name}", path=path))
                result.exported += 1
                rpd_exported = True
                result.manifest_items.append(
                    {"code": discipline.code, "status": "exported", "kind": folder}
                )
            except ValueError as exc:
                result.skipped += 1
                result.manifest_items.append(
                    {"code": discipline.code, "status": "skipped", "reason": str(exc)}
                )
        elif bucket == "gia" and program.constructor_json:
            from app.services.constructor_export import build_constructor_pdf_bytes_async

            try:
                pdf_data = await build_constructor_pdf_bytes_async(session, program, discipline)
                result.files.append(
                    _PackageFile(arcname=f"GIA/{discipline.code}.pdf", content=pdf_data)
                )
                result.exported += 1
            except ValueError:
                result.skipped += 1

        if program.fos_document_id and bucket in {"disciplines", "gia"}:
            try:
                path, _stats, name = await export_plan_discipline(
                    session,
                    plan=plan,
                    discipline=discipline,
                    doc_kind="fos",
                    force=force,
                )
                result.files.append(_PackageFile(arcname=f"FOS/{name}", path=path))
                result.exported += 1
            except ValueError:
                result.skipped += 1
        elif bucket == "gia" and program.constructor_json:
            from app.services.constructor_export import (
                build_constructor_pdf_bytes_async,
                gia_has_fos_section,
            )

            if gia_has_fos_section(program):
                try:
                    fos_pdf = await build_constructor_pdf_bytes_async(
                        session, program, discipline, fos_only=True
                    )
                    result.files.append(
                        _PackageFile(
                            arcname=f"FOS/FOS_{discipline.code}.pdf",
                            content=fos_pdf,
                        )
                    )
                    result.exported += 1
                except ValueError:
                    result.skipped += 1

        if program.document_id or program.amendments or rpd_exported:
            variant = "simple"
            if not program.amendments:
                variant = "empty"
            elif len(program.amendments) >= 2:
                variant = "transition"
            elif program.amendments[0].amendment_kind != "none":
                variant = "transition"
            dept_name = ""
            if discipline.department_code:
                dept_names = await department_names_by_codes(
                    session, {discipline.department_code}, enrollment_year=plan.year
                )
                dept_name = dept_names.get(discipline.department_code, "")
            pdf = build_reapproval_pdf_bytes(
                variant=variant,
                discipline_code=discipline.code,
                discipline_name=discipline.name,
                amendments=list(program.amendments or []),
                enrollment_year=plan.year,
                department_name=dept_name,
                signature=package_signature,
            )
            result.files.append(
                _PackageFile(
                    arcname=f"reapproval/{discipline.code}_reapproval.pdf",
                    content=pdf,
                )
            )
            result.exported += 1
            result.manifest_items.append(
                {"code": discipline.code, "status": "exported", "kind": "reapproval"}
            )

        await session.commit()

    return result


async def export_direction_year_package(
    db: AsyncSession,
    *,
    direction_code: str,
    year: int,
    force: bool = False,
) -> tuple[str, dict]:
    """Пакетный ZIP «направление + год»: папки RPD/FOS/RPP/GIA/reapproval."""
    from sqlalchemy.orm import selectinload

    from app.models import Direction, Profile
    from app.services.pdf_export import load_active_signatures
    from app.services.reapproval_export import ReapprovalSignature

    result = await db.execute(
        select(StudyPlan)
        .join(Profile, StudyPlan.profile_id == Profile.id)
        .join(Direction, Profile.direction_id == Direction.id)
        .where(Direction.code == direction_code, StudyPlan.year == year)
        .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
    )
    plans = list(result.scalars().all())
    if not plans:
        raise ValueError(f"Учебные планы не найдены: {direction_code}, {year}")

    work: list[tuple[UUID, UUID]] = []
    for plan in plans:
        disciplines = await db.execute(
            select(PlanDiscipline.id).where(PlanDiscipline.study_plan_id == plan.id)
        )
        for discipline_id in disciplines.scalars().all():
            work.append((plan.id, discipline_id))

    zip_name = f"package_{direction_code}_{year}.zip"
    zip_path = os.path.join(EXPORTS_DIR, zip_name)
    exported = 0
    skipped = 0
    manifest_items: list[dict] = []

    signatures = await load_active_signatures(db)
    dept_head = next(
        (sig for sig in signatures if sig.role in ("dept_head", "discipline_head")),
        None,
    )
    package_signature = ReapprovalSignature(
        full_name=dept_head.full_name if dept_head else "",
        png_path=dept_head.png_path if dept_head else None,
    )

    sem = asyncio.Semaphore(export_batch_max_parallel())

    async def _run_one(plan_id: UUID, discipline_id: UUID) -> _PackageDisciplineResult:
        async with sem:
            return await _export_package_discipline(
                plan_id=plan_id,
                discipline_id=discipline_id,
                force=force,
                package_signature=package_signature,
            )

    batch_results = await asyncio.gather(
        *[_run_one(plan_id, discipline_id) for plan_id, discipline_id in work],
        return_exceptions=True,
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in batch_results:
            if isinstance(item, Exception):
                skipped += 1
                manifest_items.append({"status": "error", "reason": str(item)})
                continue
            exported += item.exported
            skipped += item.skipped
            manifest_items.extend(item.manifest_items)
            for package_file in item.files:
                if package_file.content is not None:
                    zf.writestr(package_file.arcname, package_file.content)
                elif package_file.path:
                    zf.write(package_file.path, arcname=package_file.arcname)

        import json

        zf.writestr(
            "_manifest.json",
            json.dumps(
                {
                    "direction_code": direction_code,
                    "year": year,
                    "exported": exported,
                    "skipped": skipped,
                    "items": manifest_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        zf.writestr(
            "_manifest.txt",
            f"direction={direction_code}\nyear={year}\nexported={exported}\nskipped={skipped}\n",
        )

    if exported == 0:
        raise ValueError("Нет документов для пакетного экспорта")

    cleanup_exports_directory(EXPORTS_DIR)
    return zip_path, {
        "direction_code": direction_code,
        "year": year,
        "exported": exported,
        "skipped": skipped,
        "plans": len(plans),
    }
