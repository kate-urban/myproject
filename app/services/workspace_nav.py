"""Дерево навигации рабочего места: Год → Направление → Профиль → группы дисциплин."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Direction, PlanDiscipline, Profile, StudyPlan
from app.services.edit_lock import locks_for_program_ids
from app.services.rpd_extractor import RpdExtract
from app.utils.discipline_bucket import classify_discipline_bucket
from app.utils.study_plan_filters import is_test_study_plan
from app.workspace_schemas import (
    WorkspaceDirectionOut,
    WorkspaceDisciplineOut,
    WorkspacePlanOut,
    WorkspaceProfileOut,
    WorkspaceYearOut,
)


def _discipline_out(
    discipline: PlanDiscipline,
    lock_holder: str | None,
) -> WorkspaceDisciplineOut:
    program = discipline.program
    rpd = RpdExtract.from_json(program.rpd_extract_json) if program and program.rpd_extract_json else None
    return WorkspaceDisciplineOut(
        id=discipline.id,
        code=discipline.code,
        name=discipline.name,
        credits=discipline.credits,
        has_rpd=bool(program and program.document_id),
        has_fos=bool(program and program.fos_document_id),
        program_id=program.id if program else None,
        document_id=program.document_id if program else None,
        fos_document_id=program.fos_document_id if program else None,
        lock_holder=lock_holder,
        program_kind=program.program_kind if program else None,
        rpd_authors=rpd.authors if rpd else [],
        passport_needs_manual=rpd.passport_needs_manual if rpd else False,
        rpd_reapproval_years=rpd.reapproval_years if rpd else [],
    )


async def build_workspace_tree(
    db: AsyncSession,
    *,
    include_disciplines: bool = False,
) -> list[WorkspaceYearOut]:
    stmt = (
        select(StudyPlan)
        .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
        .order_by(StudyPlan.year.desc(), StudyPlan.imported_at.desc())
    )
    if include_disciplines:
        stmt = stmt.options(
            selectinload(StudyPlan.disciplines).selectinload(PlanDiscipline.program),
        )
    result = await db.execute(stmt)
    plans = list(result.scalars().all())

    lock_map = {}
    if include_disciplines:
        program_ids = [
            d.program.id
            for plan in plans
            for d in plan.disciplines
            if d.program
        ]
        lock_map = await locks_for_program_ids(db, program_ids)

    years: dict[int | None, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for plan in plans:
        profile: Profile = plan.profile
        direction: Direction = profile.direction
        if is_test_study_plan(plan, direction_code=direction.code):
            continue
        year_key = plan.year
        dir_key = direction.code

        plan_out = WorkspacePlanOut(
            id=plan.id,
            form=plan.form,
            source_file=plan.source_file,
            year=plan.year,
            direction_code=direction.code,
            direction_name=direction.name,
            profile_id=profile.id,
            profile_name=profile.name,
        )
        buckets: dict[str, list[WorkspaceDisciplineOut]] = {
            "disciplines": [],
            "practices": [],
            "gia": [],
        }
        if include_disciplines:
            for discipline in sorted(plan.disciplines, key=lambda d: (d.row_order, d.code)):
                holder = None
                if discipline.program and discipline.program.id in lock_map:
                    holder = lock_map[discipline.program.id].user_display_name
                bucket = classify_discipline_bucket(
                    code=discipline.code,
                    name=discipline.name,
                    object_type=discipline.object_type,
                )
                buckets[bucket].append(_discipline_out(discipline, holder))

        plan_out.disciplines = buckets["disciplines"]
        plan_out.practices = buckets["practices"]
        plan_out.gia = buckets["gia"]
        years[year_key][dir_key]["direction"] = direction
        years[year_key][dir_key].setdefault("profiles", {})
        years[year_key][dir_key]["profiles"].setdefault(profile.id, {"profile": profile, "plans": []})
        years[year_key][dir_key]["profiles"][profile.id]["plans"].append(plan_out)

    tree: list[WorkspaceYearOut] = []
    for year in sorted(years.keys(), key=lambda y: (y is None, y), reverse=True):
        directions: list[WorkspaceDirectionOut] = []
        for dir_code in sorted(years[year].keys()):
            node = years[year][dir_code]
            direction: Direction = node["direction"]
            profiles: list[WorkspaceProfileOut] = []
            for profile_data in node["profiles"].values():
                profile: Profile = profile_data["profile"]
                profiles.append(
                    WorkspaceProfileOut(
                        id=profile.id,
                        name=profile.name,
                        plans=sorted(
                            profile_data["plans"],
                            key=lambda p: p.source_file,
                        ),
                    )
                )
            profiles.sort(key=lambda p: p.name)
            directions.append(
                WorkspaceDirectionOut(
                    code=direction.code,
                    name=direction.name,
                    profiles=profiles,
                )
            )
        tree.append(WorkspaceYearOut(year=year, directions=directions))
    return tree
