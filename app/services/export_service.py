"""Экспорт DOCX после сверки: одна дисциплина или ZIP по плану."""

from __future__ import annotations

import io
import os
import re
import uuid
import zipfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import (
    DEFAULT_FOS_TEMPLATE_ID,
    DEFAULT_FOS_TEMPLATE_NAME,
    DEFAULT_RPD_TEMPLATE_ID,
    DEFAULT_RPD_TEMPLATE_NAME,
    EXPORT_REQUIRE_REAPPROVAL,
    EXPORT_REQUIRE_VALIDATION,
)
from app.models import Document, ExportJob, PlanDiscipline, Program, Section, StudyPlan, Template
from app.services.export_finalize import finalize_export_docx
from app.services.exporter import Exporter
from app.services.rpd_extractor import RpdExtract
from app.services.template_manager import seed_layout_templates
from app.services.validation import validate_program, validate_program_fos
from app.services.validation.section_texts import load_section_texts_by_document
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

    output_path, stats = await Exporter.export_document(
        document_id=str(document_id),
        sections_data=sections_dict,
        template_id=template_id,
        output_dir=EXPORTS_DIR,
        sections_order=sections_order,
        doc_type=doc_kind if doc_kind == "fos" else document.doc_type,
        template_name=template_name,
    )

    finalize_stats = {}
    if doc_kind == "rpd":
        finalize_stats = finalize_export_docx(
            output_path,
            rpd=rpd,
            discipline_code=discipline_code,
            discipline_name=discipline_name,
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
        report = validate_program(
            plan,
            discipline,
            program,
            section_texts=section_texts_map.get(str(document_id)),
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
        report = validate_program_fos(plan, discipline, program)
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
    if doc_kind == "rpd":
        doc_ids = [
            discipline.program.document_id
            for discipline in disciplines
            if discipline.program and discipline.program.document_id
        ]
        section_texts_by_document = await load_section_texts_by_document(db, doc_ids)

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
                )
                passed = rpd_is_passed(report.results)
            else:
                report = validate_program_fos(plan, discipline, program)
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
                )
                if rpd_is_passed(report.results):
                    rpd_passed += 1
            except ValueError:
                pass
        if program.fos_document_id:
            fos_ready += 1
            try:
                report = validate_program_fos(plan, discipline, program)
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
