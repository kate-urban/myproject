"""Библиотека РПД/ФОС на уровне направления+профиля (этапы 1–3)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Direction, PlanDiscipline, Profile, Program, StudyPlan
from app.models_tz import DirectionProgramLibrary
from app.services.fos_extractor import FosExtract
from app.services.rpd_extractor import RpdExtract
from app.services.program_extract import apply_fos_extract, apply_rpd_extract


def content_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


@dataclass
class PropagateResult:
    linked: bool = False
    discipline_code: str | None = None
    plan_discipline_id: uuid.UUID | None = None
    study_plan_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    program_status: str | None = None
    doc_kind: str | None = None
    reason: str | None = None
    propagated_plans: int = 0
    reused_document: bool = False
    library_updated: bool = False


@dataclass
class CoverageMatrix:
    direction_code: str
    profile_id: uuid.UUID
    profile_name: str
    library_rpd_count: int
    library_fos_count: int
    plans: list[dict] = field(default_factory=list)
    disciplines: list[dict] = field(default_factory=list)


async def load_profile_context(
    db: AsyncSession,
    profile_id: uuid.UUID,
) -> tuple[Direction, Profile]:
    result = await db.execute(
        select(Profile)
        .options(selectinload(Profile.direction))
        .where(Profile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ValueError("Профиль не найден")
    return profile.direction, profile


async def resolve_profile_id(
    db: AsyncSession,
    *,
    direction_code: str,
    profile_id: uuid.UUID | None = None,
    profile_name: str | None = None,
) -> uuid.UUID:
    if profile_id is not None:
        direction, profile = await load_profile_context(db, profile_id)
        if direction.code != direction_code:
            raise ValueError("profile_id не относится к указанному направлению")
        return profile.id

    stmt = (
        select(Profile)
        .join(Direction, Profile.direction_id == Direction.id)
        .where(Direction.code == direction_code)
    )
    if profile_name:
        stmt = stmt.where(Profile.name == profile_name)

    profiles = list((await db.execute(stmt)).scalars().all())
    if not profiles:
        raise ValueError(f"Профиль направления {direction_code} не найден")
    if len(profiles) > 1 and not profile_name:
        names = ", ".join(p.name for p in profiles[:5])
        raise ValueError(
            f"У направления {direction_code} несколько профилей — укажите profile_id или profile_name. "
            f"Например: {names}"
        )
    return profiles[0].id


async def find_library_document_by_hash(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID,
    file_hash: str,
    doc_kind: str,
) -> uuid.UUID | None:
    result = await db.execute(
        select(DirectionProgramLibrary.document_id)
        .where(
            DirectionProgramLibrary.profile_id == profile_id,
            DirectionProgramLibrary.content_hash == file_hash,
            DirectionProgramLibrary.doc_kind == doc_kind,
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def find_library_entry(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID,
    discipline_code: str,
    doc_kind: str,
) -> DirectionProgramLibrary | None:
    result = await db.execute(
        select(DirectionProgramLibrary).where(
            DirectionProgramLibrary.profile_id == profile_id,
            DirectionProgramLibrary.discipline_code == discipline_code,
            DirectionProgramLibrary.doc_kind == doc_kind,
        )
    )
    return result.scalar_one_or_none()


async def upsert_library_entry(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID,
    discipline_code: str,
    doc_kind: str,
    document_id: uuid.UUID,
    file_hash: str,
    source_filename: str,
    extract_json: str | None = None,
) -> DirectionProgramLibrary:
    existing = await find_library_entry(
        db,
        profile_id=profile_id,
        discipline_code=discipline_code,
        doc_kind=doc_kind,
    )
    if existing is not None:
        existing.document_id = document_id
        existing.content_hash = file_hash
        existing.source_filename = source_filename
        if extract_json is not None:
            existing.extract_json = extract_json
        await db.flush()
        return existing

    row = DirectionProgramLibrary(
        id=uuid.uuid4(),
        profile_id=profile_id,
        discipline_code=discipline_code,
        doc_kind=doc_kind,
        document_id=document_id,
        content_hash=file_hash,
        source_filename=source_filename,
        extract_json=extract_json,
    )
    db.add(row)
    await db.flush()
    return row


async def find_disciplines_for_profile_code(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID,
    discipline_code: str,
    exclude_study_plan_id: uuid.UUID | None = None,
) -> list[PlanDiscipline]:
    stmt = (
        select(PlanDiscipline)
        .join(StudyPlan, PlanDiscipline.study_plan_id == StudyPlan.id)
        .options(selectinload(PlanDiscipline.program))
        .where(
            StudyPlan.profile_id == profile_id,
            PlanDiscipline.code == discipline_code,
        )
    )
    if exclude_study_plan_id is not None:
        stmt = stmt.where(StudyPlan.id != exclude_study_plan_id)

    return list((await db.execute(stmt)).scalars().all())


async def _ensure_program(
    db: AsyncSession,
    discipline: PlanDiscipline,
) -> Program:
    if discipline.program is not None:
        return discipline.program
    program = Program(
        id=uuid.uuid4(),
        plan_discipline_id=discipline.id,
        status="missing",
    )
    db.add(program)
    discipline.program = program
    await db.flush()
    return program


async def attach_document_to_discipline(
    db: AsyncSession,
    *,
    discipline: PlanDiscipline,
    document_id: uuid.UUID,
    doc_kind: str,
    rpd: RpdExtract | None = None,
    fos: FosExtract | None = None,
    sync_structured: bool = True,
) -> Program:
    program = await _ensure_program(db, discipline)
    if doc_kind == "fos":
        program.fos_document_id = document_id
    else:
        program.document_id = document_id
    program.status = "uploaded"

    if doc_kind == "fos" and fos is not None:
        apply_fos_extract(program, fos)
    elif doc_kind == "rpd" and rpd is not None:
        apply_rpd_extract(program, rpd)
        if sync_structured:
            from app.services.structured_program_sync import sync_program_from_extract

            await sync_program_from_extract(db, program, rpd, discipline=discipline)

    await db.flush()
    return program


async def copy_extract_from_program(
    db: AsyncSession,
    target: Program,
    source: Program,
    doc_kind: str,
) -> None:
    if doc_kind == "fos":
        target.fos_extract_json = source.fos_extract_json
        return

    target.rpd_discipline_code = source.rpd_discipline_code
    target.rpd_discipline_name = source.rpd_discipline_name
    target.rpd_direction_code = source.rpd_direction_code
    target.rpd_profile_name = source.rpd_profile_name
    target.rpd_department_code = source.rpd_department_code
    target.rpd_hours_total = source.rpd_hours_total
    target.rpd_credits = source.rpd_credits
    target.rpd_competencies = source.rpd_competencies
    target.rpd_extract_json = source.rpd_extract_json

    if source.rpd_extract_json:
        rpd = RpdExtract.from_json(source.rpd_extract_json)
        discipline = await db.get(PlanDiscipline, target.plan_discipline_id)
        if discipline is not None:
            from app.services.structured_program_sync import sync_program_from_extract

            await sync_program_from_extract(db, target, rpd, discipline=discipline)


async def link_and_propagate_document(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    profile_id: uuid.UUID,
    discipline_code: str,
    doc_kind: str,
    primary_study_plan_id: uuid.UUID,
    primary_discipline: PlanDiscipline,
    propagate_all_plans: bool,
    rpd: RpdExtract | None = None,
    fos: FosExtract | None = None,
    file_hash: str | None = None,
    source_filename: str | None = None,
    reused_document: bool = False,
) -> PropagateResult:
    primary_program = await attach_document_to_discipline(
        db,
        discipline=primary_discipline,
        document_id=document_id,
        doc_kind=doc_kind,
        rpd=rpd,
        fos=fos,
        sync_structured=not reused_document,
    )

    extract_json = (
        primary_program.rpd_extract_json if doc_kind == "rpd" else primary_program.fos_extract_json
    )
    if file_hash and source_filename:
        await upsert_library_entry(
            db,
            profile_id=profile_id,
            discipline_code=discipline_code,
            doc_kind=doc_kind,
            document_id=document_id,
            file_hash=file_hash,
            source_filename=source_filename,
            extract_json=extract_json,
        )

    propagated = 0
    if propagate_all_plans:
        others = await find_disciplines_for_profile_code(
            db,
            profile_id=profile_id,
            discipline_code=discipline_code,
            exclude_study_plan_id=primary_study_plan_id,
        )
        for discipline in others:
            program = await attach_document_to_discipline(
                db,
                discipline=discipline,
                document_id=document_id,
                doc_kind=doc_kind,
                rpd=None,
                fos=None,
                sync_structured=False,
            )
            await copy_extract_from_program(db, program, primary_program, doc_kind)
            propagated += 1

    return PropagateResult(
        linked=True,
        discipline_code=discipline_code,
        plan_discipline_id=primary_discipline.id,
        study_plan_id=primary_study_plan_id,
        program_id=primary_program.id,
        program_status=primary_program.status,
        doc_kind=doc_kind,
        propagated_plans=propagated,
        reused_document=reused_document,
        library_updated=bool(file_hash),
    )


async def propagate_library_to_all_plans(
    db: AsyncSession,
    *,
    profile_id: uuid.UUID,
    discipline_code: str | None = None,
    doc_kind: str | None = None,
) -> dict:
    stmt = select(DirectionProgramLibrary).where(
        DirectionProgramLibrary.profile_id == profile_id
    )
    if discipline_code:
        stmt = stmt.where(DirectionProgramLibrary.discipline_code == discipline_code)
    if doc_kind:
        stmt = stmt.where(DirectionProgramLibrary.doc_kind == doc_kind)

    entries = list((await db.execute(stmt)).scalars().all())
    linked = skipped = 0

    for entry in entries:
        disciplines = await find_disciplines_for_profile_code(
            db,
            profile_id=profile_id,
            discipline_code=entry.discipline_code,
        )
        source_program = await _find_program_with_document(
            db, entry.document_id, entry.doc_kind
        )
        for discipline in disciplines:
            program = discipline.program
            doc_field = "fos_document_id" if entry.doc_kind == "fos" else "document_id"
            current = getattr(program, doc_field, None) if program else None
            if current == entry.document_id:
                skipped += 1
                continue
            program = await attach_document_to_discipline(
                db,
                discipline=discipline,
                document_id=entry.document_id,
                doc_kind=entry.doc_kind,
                sync_structured=False,
            )
            if source_program is not None:
                await copy_extract_from_program(db, program, source_program, entry.doc_kind)
            elif entry.extract_json:
                if entry.doc_kind == "fos":
                    program.fos_extract_json = entry.extract_json
                else:
                    program.rpd_extract_json = entry.extract_json
            linked += 1

    return {
        "library_entries": len(entries),
        "programs_linked": linked,
        "programs_skipped": skipped,
    }


async def _find_program_with_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    doc_kind: str,
) -> Program | None:
    if doc_kind == "fos":
        clause = Program.fos_document_id == document_id
    else:
        clause = Program.document_id == document_id
    result = await db.execute(select(Program).where(clause).limit(1))
    return result.scalar_one_or_none()


async def build_coverage_matrix(
    db: AsyncSession,
    *,
    direction_code: str,
    profile_id: uuid.UUID,
) -> CoverageMatrix:
    direction, profile = await load_profile_context(db, profile_id)
    if direction.code != direction_code:
        raise ValueError("profile_id не относится к направлению")

    lib_result = await db.execute(
        select(DirectionProgramLibrary).where(
            DirectionProgramLibrary.profile_id == profile_id
        )
    )
    library = list(lib_result.scalars().all())
    lib_rpd = {e.discipline_code: e for e in library if e.doc_kind == "rpd"}
    lib_fos = {e.discipline_code: e for e in library if e.doc_kind == "fos"}

    plans_result = await db.execute(
        select(StudyPlan)
        .options(
            selectinload(StudyPlan.disciplines).selectinload(PlanDiscipline.program),
        )
        .where(StudyPlan.profile_id == profile_id)
        .order_by(StudyPlan.year.desc().nullslast(), StudyPlan.form)
    )
    plans = list(plans_result.scalars().all())

    plan_rows: list[dict] = []
    discipline_codes: set[str] = set(lib_rpd.keys()) | set(lib_fos.keys())

    for plan in plans:
        total = len(plan.disciplines)
        linked_rpd = 0
        linked_fos = 0
        for disc in plan.disciplines:
            discipline_codes.add(disc.code)
            prog = disc.program
            if prog and prog.document_id:
                linked_rpd += 1
            if prog and prog.fos_document_id:
                linked_fos += 1
        plan_rows.append(
            {
                "study_plan_id": str(plan.id),
                "year": plan.year,
                "form": plan.form,
                "source_file": plan.source_file,
                "disciplines_total": total,
                "rpd_linked": linked_rpd,
                "fos_linked": linked_fos,
                "rpd_coverage_pct": round(100 * linked_rpd / total, 1) if total else 0,
                "library_rpd_available": sum(
                    1 for d in plan.disciplines if d.code in lib_rpd
                ),
            }
        )

    discipline_rows: list[dict] = []
    for code in sorted(discipline_codes):
        in_plans = sum(1 for p in plans for d in p.disciplines if d.code == code)
        linked_plans = 0
        for plan in plans:
            for disc in plan.disciplines:
                if disc.code != code:
                    continue
                prog = disc.program
                if prog and (prog.document_id or prog.fos_document_id):
                    linked_plans += 1
        discipline_rows.append(
            {
                "discipline_code": code,
                "in_library_rpd": code in lib_rpd,
                "in_library_fos": code in lib_fos,
                "plans_with_discipline": in_plans,
                "plans_linked": linked_plans,
            }
        )

    return CoverageMatrix(
        direction_code=direction.code,
        profile_id=profile.id,
        profile_name=profile.name,
        library_rpd_count=len(lib_rpd),
        library_fos_count=len(lib_fos),
        plans=plan_rows,
        disciplines=discipline_rows,
    )


def doc_kind_from_filename(filename: str) -> str:
    return "fos" if Path(filename).stem.upper().startswith("FOS_") else "rpd"
