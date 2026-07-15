"""API реляционного тела программы (topics / zuv / literature) — ТЗ P2."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.program_content import (
    get_program_structured,
    refresh_structured_from_document,
    replace_program_literature,
    replace_program_topics,
    replace_program_zuv,
)

router = APIRouter(prefix="/programs", tags=["program-content"])


class TopicIn(BaseModel):
    topic_number: str
    title: str
    semester: int | None = None
    hours_lecture: int | None = None
    hours_practical: int | None = None
    hours_lab: int | None = None
    hours_sr: int | None = None
    is_bold: bool = False
    row_order: int | None = None


class ZuvIn(BaseModel):
    indicator_code: str
    zuv_type: str = "know"
    text: str
    topic_ref: str | None = None


class LiteratureIn(BaseModel):
    citation: str
    lit_type: str | None = None
    row_order: int | None = None


class TopicsReplaceIn(BaseModel):
    items: list[TopicIn] = Field(default_factory=list)


class ZuvReplaceIn(BaseModel):
    items: list[ZuvIn] = Field(default_factory=list)


class LiteratureReplaceIn(BaseModel):
    items: list[LiteratureIn] = Field(default_factory=list)


@router.post("/{program_id}/structured/apply-to-document/")
async def apply_program_structured_to_document(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    from app.services.structured_to_document import apply_structured_to_document

    try:
        result = await apply_structured_to_document(db, program_id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.post("/{program_id}/structured/refresh-from-document/")
async def refresh_program_structured_from_document(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await refresh_structured_from_document(db, program_id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.get("/{program_id}/structured/")
async def read_program_structured(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await get_program_structured(db, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{program_id}/topics/")
async def read_program_topics(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        payload = await get_program_structured(db, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return payload["topics"]


@router.put("/{program_id}/topics/")
async def write_program_topics(
    program_id: UUID,
    body: TopicsReplaceIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await replace_program_topics(
            db,
            program_id,
            [item.model_dump() for item in body.items],
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"items": items}


@router.get("/{program_id}/zuv/")
async def read_program_zuv(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        payload = await get_program_structured(db, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return payload["zuv"]


@router.put("/{program_id}/zuv/")
async def write_program_zuv(
    program_id: UUID,
    body: ZuvReplaceIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await replace_program_zuv(
            db,
            program_id,
            [item.model_dump() for item in body.items],
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"items": items}


@router.get("/{program_id}/literature/")
async def read_program_literature(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        payload = await get_program_structured(db, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return payload["literature"]


@router.put("/{program_id}/literature/")
async def write_program_literature(
    program_id: UUID,
    body: LiteratureReplaceIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await replace_program_literature(
            db,
            program_id,
            [item.model_dump() for item in body.items],
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"items": items}
