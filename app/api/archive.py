"""Архивные тома (модуль 5 ТЗ)."""

from __future__ import annotations

import base64
import io
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import PlanDiscipline, Program
from app.models_tz import ArchiveVolume, ArchiveVolumeItem
from app.services.archive_export import (
    build_certification_text,
    build_inventory_text,
    build_volume_pdf_bytes,
    count_pdf_pages,
    load_study_plan_for_archive,
)

router = APIRouter(prefix="/archive", tags=["archive"])


class ArchiveVolumeIn(BaseModel):
    study_plan_id: UUID
    title: str
    cover_text: str | None = None


class ArchiveVolumePatch(BaseModel):
    title: str | None = None
    cover_text: str | None = None
    inventory_text: str | None = None
    status: str | None = None
    duplex_enabled: bool | None = None


@router.get("/volumes/")
async def list_volumes(study_plan_id: UUID | None = None, db: AsyncSession = Depends(get_db)):
    query = select(ArchiveVolume).order_by(ArchiveVolume.created_at.desc())
    if study_plan_id:
        query = query.where(ArchiveVolume.study_plan_id == study_plan_id)
    result = await db.execute(query)
    return [
        {
            "id": str(v.id),
            "study_plan_id": str(v.study_plan_id),
            "title": v.title,
            "status": v.status,
            "has_inventory": bool(v.inventory_text),
        }
        for v in result.scalars().all()
    ]


@router.get("/volumes/{volume_id}/")
async def get_volume(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ArchiveVolume)
        .options(selectinload(ArchiveVolume.items).selectinload(ArchiveVolumeItem.program))
        .where(ArchiveVolume.id == volume_id)
    )
    volume = result.scalar_one_or_none()
    if volume is None:
        raise HTTPException(status_code=404, detail="Том не найден")

    disc_map: dict[str, dict] = {}
    if volume.items:
        program_ids = [item.program_id for item in volume.items]
        rows = await db.execute(
            select(PlanDiscipline, Program)
            .join(Program, Program.plan_discipline_id == PlanDiscipline.id)
            .where(Program.id.in_(program_ids))
        )
        for discipline, program in rows.all():
            disc_map[str(program.id)] = {
                "code": discipline.code,
                "name": discipline.name,
            }

    return {
        "id": str(volume.id),
        "study_plan_id": str(volume.study_plan_id),
        "title": volume.title,
        "status": volume.status,
        "cover_text": volume.cover_text,
        "inventory_text": volume.inventory_text,
        "duplex_enabled": bool(getattr(volume, "duplex_enabled", True)),
        "items": [
            {
                "id": str(item.id),
                "program_id": str(item.program_id),
                "row_order": item.row_order,
                "sheet_count": item.sheet_count,
                "page_start": item.page_start,
                "page_end": item.page_end,
                "discipline": disc_map.get(str(item.program_id)),
            }
            for item in sorted(volume.items, key=lambda row: row.row_order)
        ],
    }


@router.post("/volumes/")
async def create_volume(body: ArchiveVolumeIn, db: AsyncSession = Depends(get_db)):
    plan = await load_study_plan_for_archive(db, body.study_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    volume = ArchiveVolume(
        study_plan_id=body.study_plan_id,
        title=body.title,
        cover_text=body.cover_text,
        status="draft",
    )
    if not volume.cover_text:
        volume.cover_text = build_certification_text(volume, plan)
    db.add(volume)
    await db.flush()
    await db.commit()
    return {"id": str(volume.id)}


@router.delete("/volumes/{volume_id}/")
async def delete_volume(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    volume = await db.get(ArchiveVolume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="Том не найден")
    await db.execute(delete(ArchiveVolumeItem).where(ArchiveVolumeItem.volume_id == volume_id))
    await db.delete(volume)
    await db.commit()
    return None


@router.patch("/volumes/{volume_id}/")
async def patch_volume(
    volume_id: UUID,
    body: ArchiveVolumePatch,
    db: AsyncSession = Depends(get_db),
):
    volume = await db.get(ArchiveVolume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="Том не найден")
    for field in ("title", "cover_text", "inventory_text", "status", "duplex_enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(volume, field, value)
    await db.commit()
    return {"id": str(volume.id), "status": volume.status}


@router.get("/certification-template/")
async def certification_template(
    study_plan_id: UUID,
    title: str = "Архивный том",
    db: AsyncSession = Depends(get_db),
):
    plan = await load_study_plan_for_archive(db, study_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Учебный план не найден")
    volume = ArchiveVolume(study_plan_id=study_plan_id, title=title, status="draft")
    return {"text": build_certification_text(volume, plan)}


@router.post("/volumes/{volume_id}/populate-from-plan/")
async def populate_volume_from_plan(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    volume = await db.get(ArchiveVolume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="Том не найден")

    await db.execute(delete(ArchiveVolumeItem).where(ArchiveVolumeItem.volume_id == volume.id))

    result = await db.execute(
        select(Program)
        .join(PlanDiscipline, Program.plan_discipline_id == PlanDiscipline.id)
        .where(PlanDiscipline.study_plan_id == volume.study_plan_id)
    )
    programs = list(result.scalars().all())
    order = 0
    for program in programs:
        program.is_archived = True
        db.add(
            ArchiveVolumeItem(
                volume_id=volume.id,
                program_id=program.id,
                row_order=order,
            )
        )
        order += 1
    volume.status = "ready"
    plan = await load_study_plan_for_archive(db, volume.study_plan_id)
    if plan and not volume.cover_text:
        volume.cover_text = build_certification_text(volume, plan)

    disciplines = {
        row.id: row
        for row in (
            await db.execute(
                select(PlanDiscipline).where(PlanDiscipline.study_plan_id == volume.study_plan_id)
            )
        ).scalars().all()
    }
    programs_map = {program.id: program for program in programs}
    items = (
        await db.execute(
            select(ArchiveVolumeItem).where(ArchiveVolumeItem.volume_id == volume.id)
        )
    ).scalars().all()
    volume.inventory_text = build_inventory_text(volume, list(items), disciplines, programs_map)
    await db.commit()
    return {"items": order}


@router.post("/volumes/{volume_id}/build-inventory/")
async def rebuild_inventory(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ArchiveVolume)
        .options(selectinload(ArchiveVolume.items))
        .where(ArchiveVolume.id == volume_id)
    )
    volume = result.scalar_one_or_none()
    if volume is None:
        raise HTTPException(status_code=404, detail="Том не найден")
    disciplines = {
        row.id: row
        for row in (
            await db.execute(
                select(PlanDiscipline).where(PlanDiscipline.study_plan_id == volume.study_plan_id)
            )
        ).scalars().all()
    }
    program_ids = [item.program_id for item in volume.items]
    programs_map = {}
    if program_ids:
        programs_map = {
            row.id: row
            for row in (
                await db.execute(select(Program).where(Program.id.in_(program_ids)))
            ).scalars().all()
        }
    volume.inventory_text = build_inventory_text(volume, volume.items, disciplines, programs_map)
    await db.commit()
    return {"inventory_text": volume.inventory_text}


@router.get("/volumes/{volume_id}/export.pdf")
async def export_volume_pdf(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        pdf_bytes, warnings = await build_volume_pdf_bytes(db, volume_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    headers = {
        "Content-Disposition": f'attachment; filename="archive_{volume_id}.pdf"',
        "X-Archive-Pages": str(count_pdf_pages(pdf_bytes)),
    }
    if warnings:
        encoded = base64.b64encode(" | ".join(warnings)[:2000].encode("utf-8")).decode("ascii")
        headers["X-Archive-Warnings"] = encoded
        headers["X-Archive-Warnings-Encoding"] = "base64-utf8"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=headers,
    )


@router.get("/volumes/{volume_id}/export.zip")
async def export_volume_zip(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    volume = await db.get(ArchiveVolume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="Том не найден")
    try:
        pdf_bytes, _warnings = await build_volume_pdf_bytes(db, volume_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.refresh(volume)
    safe_title = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in volume.title)[:80]
    disciplines = {
        row.id: row
        for row in (
            await db.execute(
                select(PlanDiscipline).where(PlanDiscipline.study_plan_id == volume.study_plan_id)
            )
        ).scalars().all()
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{safe_title}.pdf", pdf_bytes)
        if volume.inventory_text:
            archive.writestr("inventory.txt", volume.inventory_text.encode("utf-8"))
        if volume.cover_text:
            archive.writestr("certification.txt", volume.cover_text.encode("utf-8"))

        from app.services.layout_archive_export import export_document_docx_via_layout

        for item in sorted(volume.items, key=lambda row: row.row_order):
            program = await db.get(Program, item.program_id)
            if program is None:
                continue
            disc = disciplines.get(program.plan_discipline_id)
            if disc is None:
                continue
            safe_code = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in disc.code)[:40]
            if program.document_id:
                docx = await export_document_docx_via_layout(
                    db,
                    document_id=program.document_id,
                    doc_kind="rpd",
                    discipline=disc,
                    program=program,
                )
                if docx:
                    archive.writestr(f"word/{safe_code}_RPD.docx", docx[0])
            elif program.constructor_json:
                from app.services.constructor_export import export_constructor_via_layout

                layout = await export_constructor_via_layout(db, program, disc)
                if layout:
                    archive.writestr(f"word/{safe_code}_program.docx", layout[0])
    await db.commit()
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="archive_{volume_id}.zip"',
            "X-Archive-Pages": str(count_pdf_pages(pdf_bytes)),
        },
    )
