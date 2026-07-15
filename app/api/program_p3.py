"""API P3: МТО ↔ аудитории, автосборка аннотации."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.p3_assemble import (
    apply_annotation_text,
    apply_mto_text,
    build_annotation_suggestion,
    build_mto_suggestion,
    list_program_mto_rooms,
    load_program_with_discipline,
    replace_program_mto_rooms,
)

router = APIRouter(prefix="/programs", tags=["program-p3"])


class MtoRoomsIn(BaseModel):
    room_ids: list[UUID] = Field(default_factory=list)


class TextApplyIn(BaseModel):
    text: str | None = None


@router.get("/{program_id}/mto/rooms/")
async def read_program_mto_rooms(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        await load_program_with_discipline(db, program_id)
        rooms = await list_program_mto_rooms(db, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "program_id": str(program_id),
        "rooms": [
            {
                "id": str(room.id),
                "code": room.code,
                "name": room.name,
                "equipment": room.equipment,
                "building": room.building,
            }
            for room in rooms
        ],
    }


@router.put("/{program_id}/mto/rooms/")
async def write_program_mto_rooms(
    program_id: UUID,
    body: MtoRoomsIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        await load_program_with_discipline(db, program_id)
        rooms = await replace_program_mto_rooms(db, program_id, body.room_ids)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "program_id": str(program_id),
        "rooms": [{"id": str(room.id), "code": room.code, "name": room.name} for room in rooms],
    }


@router.get("/{program_id}/mto/suggest/")
async def suggest_program_mto(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        await load_program_with_discipline(db, program_id)
        text = await build_mto_suggestion(db, program_id)
        rooms = await list_program_mto_rooms(db, program_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"program_id": str(program_id), "text": text, "room_count": len(rooms)}


@router.post("/{program_id}/mto/apply/")
async def apply_program_mto(
    program_id: UUID,
    body: TextApplyIn | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        program, discipline, _plan = await load_program_with_discipline(db, program_id)
        text = (body.text if body and body.text else None) or await build_mto_suggestion(
            db, program_id
        )
        result = await apply_mto_text(db, program, discipline, text)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"program_id": str(program_id), "text": text, **result}


@router.get("/{program_id}/annotation/suggest/")
async def suggest_program_annotation(program_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        program, discipline, plan = await load_program_with_discipline(db, program_id)
        text = await build_annotation_suggestion(db, program, discipline, plan)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"program_id": str(program_id), "text": text}


@router.post("/{program_id}/annotation/apply/")
async def apply_program_annotation(
    program_id: UUID,
    body: TextApplyIn | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        program, discipline, plan = await load_program_with_discipline(db, program_id)
        text = (body.text if body and body.text else None) or await build_annotation_suggestion(
            db, program, discipline, plan
        )
        result = await apply_annotation_text(db, program, discipline, text)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"program_id": str(program_id), "text": text, **result}
