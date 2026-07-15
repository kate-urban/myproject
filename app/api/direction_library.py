"""API библиотеки РПД/ФОС на уровне направления (этапы 1–3)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import BatchUploadOut
from app.services.direction_library import (
    build_coverage_matrix,
    propagate_library_to_all_plans,
    resolve_profile_id,
)
from app.services.document_upload import batch_ingest_documents

router = APIRouter(prefix="/directions", tags=["direction-library"])


class PropagateOut(BaseModel):
    library_entries: int
    programs_linked: int
    programs_skipped: int


class CoveragePlanOut(BaseModel):
    study_plan_id: str
    year: int | None
    form: str
    source_file: str
    disciplines_total: int
    rpd_linked: int
    fos_linked: int
    rpd_coverage_pct: float
    library_rpd_available: int


class CoverageDisciplineOut(BaseModel):
    discipline_code: str
    in_library_rpd: bool
    in_library_fos: bool
    plans_with_discipline: int
    plans_linked: int


class CoverageMatrixOut(BaseModel):
    direction_code: str
    profile_id: uuid.UUID
    profile_name: str
    library_rpd_count: int
    library_fos_count: int
    plans: list[CoveragePlanOut]
    disciplines: list[CoverageDisciplineOut]


@router.post("/{direction_code}/library/batch-upload/", response_model=BatchUploadOut)
async def batch_upload_direction_library(
    direction_code: str,
    files: list[UploadFile] = File(...),
    profile_id: Optional[uuid.UUID] = Query(None),
    profile_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Загрузка папки РПД в библиотеку направления с привязкой ко всем планам профиля."""
    if not files:
        raise HTTPException(status_code=400, detail="Не выбраны файлы")
    try:
        resolved_profile_id = await resolve_profile_id(
            db,
            direction_code=direction_code,
            profile_id=profile_id,
            profile_name=profile_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await batch_ingest_documents(
        db,
        profile_id=resolved_profile_id,
        propagate_all_plans=True,
        uploads=files,
    )


@router.post("/{direction_code}/library/propagate/", response_model=PropagateOut)
async def propagate_direction_library(
    direction_code: str,
    profile_id: Optional[uuid.UUID] = Query(None),
    profile_name: Optional[str] = Query(None),
    discipline_code: Optional[str] = Query(None),
    doc_kind: Optional[str] = Query(None, pattern="^(rpd|fos)$"),
    db: AsyncSession = Depends(get_db),
):
    """Перепривязать документы из библиотеки ко всем учебным планам профиля."""
    try:
        resolved_profile_id = await resolve_profile_id(
            db,
            direction_code=direction_code,
            profile_id=profile_id,
            profile_name=profile_name,
        )
        result = await propagate_library_to_all_plans(
            db,
            profile_id=resolved_profile_id,
            discipline_code=discipline_code,
            doc_kind=doc_kind,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PropagateOut(**result)


@router.get("/{direction_code}/coverage-matrix/", response_model=CoverageMatrixOut)
async def direction_coverage_matrix(
    direction_code: str,
    profile_id: Optional[uuid.UUID] = Query(None),
    profile_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Матрица покрытия: библиотека РПД × учебные планы (годы/формы)."""
    try:
        resolved_profile_id = await resolve_profile_id(
            db,
            direction_code=direction_code,
            profile_id=profile_id,
            profile_name=profile_name,
        )
        matrix = await build_coverage_matrix(
            db,
            direction_code=direction_code,
            profile_id=resolved_profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CoverageMatrixOut(
        direction_code=matrix.direction_code,
        profile_id=matrix.profile_id,
        profile_name=matrix.profile_name,
        library_rpd_count=matrix.library_rpd_count,
        library_fos_count=matrix.library_fos_count,
        plans=[CoveragePlanOut(**row) for row in matrix.plans],
        disciplines=[CoverageDisciplineOut(**row) for row in matrix.disciplines],
    )
