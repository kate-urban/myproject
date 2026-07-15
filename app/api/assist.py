"""API ИИ-помощника методиста на странице сверки."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth_deps import get_current_user
from app.config import ai_assistant_enabled, ai_llm_configured
from app.database import get_db
from app.models import PlanDiscipline, Profile, Section, StudyPlan
from app.schemas import (
    ValidationAssistIn,
    ValidationAssistOut,
    ValidationFixChangeOut,
    ValidationSuggestFixIn,
    ValidationSuggestFixOut,
)
from app.services.ai_assistant import assist_validation
from app.services.ai_fix import suggest_llm_validation_fix
from app.services.auth import CurrentUser
from app.services.validation.engine import _build_context, _rpd_from_program, validate_program
from app.services.validation_fix import SUPPORTED_RULE_IDS, suggest_validation_fix

router = APIRouter(prefix="/assist", tags=["assist"])


def _fix_to_out(fix) -> ValidationSuggestFixOut:
    return ValidationSuggestFixOut(
        rule_id=fix.rule_id,
        supported=fix.supported,
        apply_safe=fix.apply_safe,
        patched_html=fix.patched_html,
        changes=[
            ValidationFixChangeOut(
                field=c.field,
                old=c.old,
                new=c.new,
                row_label=c.row_label,
            )
            for c in fix.changes
        ],
        message=fix.message,
        source=getattr(fix, "source", "deterministic"),
        explanation=getattr(fix, "explanation", None),
    )


async def _prepare_fix_context(
    db: AsyncSession,
    body: ValidationSuggestFixIn,
    rule_id: str,
):
    section = await db.get(Section, body.section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Раздел не найден")

    plan, discipline = await _load_discipline_for_fix(db, body.study_plan_id, body.discipline_id)
    rpd = _rpd_from_program(discipline.program)
    if rpd is None:
        raise HTTPException(status_code=422, detail="Не удалось загрузить данные РПД")

    ctx = _build_context(plan, discipline, rpd)
    report = validate_program(plan, discipline, discipline.program, rule_ids=[rule_id])
    rule_result = next((r for r in report.results if r.rule_id == rule_id), None)
    if rule_result is None:
        raise HTTPException(status_code=422, detail=f"Правило {rule_id} не найдено")
    return section, plan, discipline, ctx, rule_result


async def _load_discipline_for_fix(
    db: AsyncSession,
    plan_id: UUID,
    discipline_id: UUID,
) -> tuple[StudyPlan, PlanDiscipline]:
    plan = (
        await db.execute(
            select(StudyPlan)
            .options(selectinload(StudyPlan.profile).selectinload(Profile.direction))
            .where(StudyPlan.id == plan_id)
        )
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")

    discipline = (
        await db.execute(
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
    ).scalar_one_or_none()
    if discipline is None:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    if discipline.program is None:
        raise HTTPException(status_code=422, detail="РПД не привязана к дисциплине")
    return plan, discipline


@router.post("/validation/", response_model=ValidationAssistOut)
async def explain_validation_error(
    body: ValidationAssistIn,
    _user: CurrentUser = Depends(get_current_user),
):
    if not ai_assistant_enabled():
        raise HTTPException(status_code=503, detail="ИИ-помощник отключён (AI_ASSISTANT_ENABLED=false)")

    kind = body.kind if body.kind in ("rpd", "fos") else "rpd"
    answer, source = await assist_validation(
        question=body.question,
        rule_id=body.rule_id,
        kind=kind,
        discipline_code=body.discipline_code,
        rule_name=body.rule_name,
        message=body.message,
        expected=body.expected,
        actual=body.actual,
        section_title=body.section_title,
        section_snippet=body.section_snippet,
    )
    return ValidationAssistOut(answer=answer, source=source)


@router.post("/suggest-fix/", response_model=ValidationSuggestFixOut)
async def suggest_validation_fix_endpoint(
    body: ValidationSuggestFixIn,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    rule_id = (body.rule_id or "").upper()
    if rule_id not in SUPPORTED_RULE_IDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Автоправка для {rule_id} не поддерживается. "
                f"Доступны: {', '.join(sorted(SUPPORTED_RULE_IDS))}. "
                "Для других правил используйте /assist/suggest-fix-llm/"
            ),
        )

    _section, _plan, discipline, ctx, rule_result = await _prepare_fix_context(db, body, rule_id)
    fix = suggest_validation_fix(rule_id, body.section_html, ctx, rule_result)
    return _fix_to_out(fix)


@router.post("/suggest-fix-llm/", response_model=ValidationSuggestFixOut)
async def suggest_validation_fix_llm_endpoint(
    body: ValidationSuggestFixIn,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    if not ai_assistant_enabled():
        raise HTTPException(status_code=503, detail="ИИ-помощник отключён (AI_ASSISTANT_ENABLED=false)")
    if not ai_llm_configured():
        raise HTTPException(status_code=503, detail="LLM не настроен — добавьте AI_API_KEY в .env")

    rule_id = (body.rule_id or "").upper()
    if not rule_id:
        raise HTTPException(status_code=422, detail="Укажите rule_id")

    section, _plan, discipline, ctx, rule_result = await _prepare_fix_context(db, body, rule_id)
    if rule_result.passed or rule_result.skipped:
        raise HTTPException(status_code=422, detail="Правило уже выполнено или пропущено")

    fix = await suggest_llm_validation_fix(
        rule_id,
        body.section_html,
        ctx,
        rule_result,
        kind="rpd",
        section_title=section.section_name,
        discipline_code=discipline.code,
    )
    return _fix_to_out(fix)
