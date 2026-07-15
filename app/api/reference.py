"""CRUD справочников по ТЗ."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth_deps import get_current_user
from app.services.auth import CurrentUser
from app.services.department_lookup import resolve_department_name
from app.services.signature_storage import (
    ALLOWED_SUFFIXES,
    store_signature_file,
)
from app.utils.http_errors import public_error_message
from app.utils.upload_limits import read_upload_bytes
from app.models_tz import (
    RefAbbreviation,
    RefDepartment,
    RefFgosCompetency,
    RefFgosIndicator,
    RefMtoRoom,
    RefPhrase,
    RefSignature,
)

router = APIRouter(prefix="/reference", tags=["reference"])


class FgosCompetencyIn(BaseModel):
    kind: str
    code: str
    group_code: str | None = None
    title: str
    fgos_version: str | None = None


class FgosCompetencyUpdate(BaseModel):
    kind: str | None = None
    code: str | None = None
    group_code: str | None = None
    title: str | None = None
    fgos_version: str | None = None


class FgosIndicatorIn(BaseModel):
    competency_id: UUID
    code: str
    title: str


class FgosIndicatorUpdate(BaseModel):
    competency_id: UUID | None = None
    code: str | None = None
    title: str | None = None


class DepartmentIn(BaseModel):
    code: str
    name: str
    opened_on: str | None = None
    closed_on: str | None = None
    parent_id: UUID | None = None


class DepartmentUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    opened_on: str | None = None
    closed_on: str | None = None
    parent_id: UUID | None = None


class SignatureIn(BaseModel):
    role: str
    full_name: str
    png_path: str | None = None


class SignatureUpdate(BaseModel):
    role: str | None = None
    full_name: str | None = None


class AbbreviationIn(BaseModel):
    pattern: str
    replacement: str
    priority: int = 0
    is_regex: bool = False


class AbbreviationUpdate(BaseModel):
    pattern: str | None = None
    replacement: str | None = None
    priority: int | None = None
    is_regex: bool | None = None


class PhraseIn(BaseModel):
    category: str
    text: str
    version: int = 1
    is_active: bool = True


class PhraseUpdate(BaseModel):
    category: str | None = None
    text: str | None = None
    version: int | None = None
    is_active: bool | None = None


class MtoRoomIn(BaseModel):
    code: str
    name: str
    equipment: str | None = None
    building: str | None = None


class MtoRoomUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    equipment: str | None = None
    building: str | None = None


@router.get("/fgos/competencies/")
async def list_fgos_competencies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RefFgosCompetency).order_by(RefFgosCompetency.code))
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "code": row.code,
            "group_code": row.group_code,
            "title": row.title,
            "fgos_version": row.fgos_version,
        }
        for row in result.scalars().all()
    ]


@router.post("/fgos/competencies/")
async def create_fgos_competency(body: FgosCompetencyIn, db: AsyncSession = Depends(get_db)):
    row = RefFgosCompetency(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/fgos/competencies/{row_id}/")
async def delete_fgos_competency(row_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(RefFgosCompetency, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Компетенция не найдена")
    await db.delete(row)
    await db.commit()
    return None


@router.put("/fgos/competencies/{row_id}/")
async def update_fgos_competency(
    row_id: UUID,
    body: FgosCompetencyUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(RefFgosCompetency, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Компетенция не найдена")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.get("/fgos/indicators/")
async def list_fgos_indicators(
    competency_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(RefFgosIndicator).order_by(RefFgosIndicator.code)
    if competency_id:
        query = query.where(RefFgosIndicator.competency_id == competency_id)
    result = await db.execute(query)
    return [
        {
            "id": str(row.id),
            "competency_id": str(row.competency_id),
            "code": row.code,
            "title": row.title,
        }
        for row in result.scalars().all()
    ]


@router.post("/fgos/indicators/")
async def create_fgos_indicator(body: FgosIndicatorIn, db: AsyncSession = Depends(get_db)):
    row = RefFgosIndicator(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/fgos/indicators/{row_id}/")
async def delete_fgos_indicator(row_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(RefFgosIndicator, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Индикатор не найден")
    await db.delete(row)
    await db.commit()
    return None


@router.put("/fgos/indicators/{row_id}/")
async def update_fgos_indicator(
    row_id: UUID,
    body: FgosIndicatorUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(RefFgosIndicator, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Индикатор не найден")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.get("/departments/")
async def list_departments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefDepartment).order_by(RefDepartment.code, RefDepartment.opened_on.desc().nullslast())
    )
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "name": r.name,
            "opened_on": r.opened_on.isoformat() if r.opened_on else None,
            "closed_on": r.closed_on.isoformat() if r.closed_on else None,
            "parent_id": str(r.parent_id) if r.parent_id else None,
        }
        for r in result.scalars().all()
    ]


@router.post("/departments/")
async def create_department(body: DepartmentIn, db: AsyncSession = Depends(get_db)):
    from datetime import date

    opened = date.fromisoformat(body.opened_on) if body.opened_on else None
    closed = date.fromisoformat(body.closed_on) if body.closed_on else None
    row = RefDepartment(
        code=body.code,
        name=body.name,
        opened_on=opened,
        closed_on=closed,
        parent_id=body.parent_id,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/departments/{row_id}/")
async def delete_department(row_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(RefDepartment, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Кафедра не найдена")
    await db.delete(row)
    await db.commit()
    return None


@router.put("/departments/{row_id}/")
async def update_department(
    row_id: UUID,
    body: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    from datetime import date

    row = await db.get(RefDepartment, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Кафедра не найдена")
    data = body.model_dump(exclude_unset=True)
    for key in ("opened_on", "closed_on"):
        if key in data:
            raw = data[key]
            data[key] = date.fromisoformat(raw) if raw else None
    for key, value in data.items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.post("/departments/import/")
async def import_departments_xlsx(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Массовый импорт кафедр из Excel (код + название)."""
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Ожидается файл .xlsx")

    from app.services.department_import import parse_departments_from_bytes, persist_department_rows

    content = await read_upload_bytes(file)
    if not content:
        raise HTTPException(status_code=422, detail="Пустой файл")

    try:
        rows, warnings = parse_departments_from_bytes(content)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=public_error_message(exc, fallback="Не удалось прочитать Excel"),
        ) from exc

    if not rows:
        detail = warnings[0] if warnings else "В файле нет пар «код + название кафедры»"
        raise HTTPException(status_code=422, detail={"message": detail, "warnings": warnings})

    result = await persist_department_rows(db, rows)
    result["warnings"] = warnings
    return result


@router.get("/departments/resolve/")
async def resolve_department(
    code: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Название кафедры по коду (с учётом года набора) — для отчёта 7.1 и UI."""
    name = await resolve_department_name(db, code, enrollment_year=year)
    return {
        "code": code.strip(),
        "year": year,
        "name": name,
        "found": bool(name),
    }


@router.get("/fgos/check/")
async def check_fgos_codes(
    indicator: str | None = None,
    competency: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """P2: проверка кодов ФГОС перед вводом в РПД/конструктор."""
    out: dict = {"indicator": indicator, "competency": competency, "indicator_ok": None, "competency_ok": None}
    if competency:
        comp_norm = competency.strip().upper()
        comp = (
            await db.execute(
                select(RefFgosCompetency).where(func.upper(RefFgosCompetency.code) == comp_norm)
            )
        ).scalar_one_or_none()
        out["competency_ok"] = comp is not None
        out["competency_title"] = comp.title if comp else None
    if indicator:
        ind_norm = indicator.strip().upper()
        ind = (
            await db.execute(
                select(RefFgosIndicator).where(func.upper(RefFgosIndicator.code) == ind_norm)
            )
        ).scalar_one_or_none()
        out["indicator_ok"] = ind is not None
        out["indicator_title"] = ind.title if ind else None
    return out


@router.get("/signatures/")
async def list_signatures(
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    result = await db.execute(select(RefSignature).where(RefSignature.is_active.is_(True)))
    return [
        {
            "id": str(r.id),
            "role": r.role,
            "full_name": r.full_name,
            "has_png": bool((r.png_path or "").strip()),
        }
        for r in result.scalars().all()
    ]


@router.post("/signatures/")
async def create_signature(
    body: SignatureIn,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    row = RefSignature(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/signatures/{row_id}/")
async def delete_signature(
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    row = await db.get(RefSignature, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Подпись не найдена")
    row.is_active = False
    await db.commit()
    return None


@router.put("/signatures/{row_id}/")
async def update_signature(
    row_id: UUID,
    body: SignatureUpdate,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    row = await db.get(RefSignature, row_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Подпись не найдена")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.post("/signatures/{row_id}/png/")
async def upload_signature_png(
    row_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    from pathlib import Path

    row = await db.get(RefSignature, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Подпись не найдена")
    suffix = Path(file.filename or "sig.png").suffix.lower()
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/") and suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Ожидается PNG/JPEG")
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".png"
    row.png_path = store_signature_file(row_id, await read_upload_bytes(file), suffix)
    await db.flush()
    await db.commit()
    return {"has_png": True}


@router.get("/abbreviations/")
async def list_abbreviations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefAbbreviation)
        .where(RefAbbreviation.is_active.is_(True))
        .order_by(RefAbbreviation.priority.desc())
    )
    return [
        {
            "id": str(r.id),
            "pattern": r.pattern,
            "replacement": r.replacement,
            "priority": r.priority,
            "is_regex": r.is_regex,
        }
        for r in result.scalars().all()
    ]


@router.post("/abbreviations/")
async def create_abbreviation(body: AbbreviationIn, db: AsyncSession = Depends(get_db)):
    row = RefAbbreviation(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/abbreviations/{row_id}/")
async def delete_abbreviation(row_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(RefAbbreviation, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    row.is_active = False
    await db.flush()
    await db.commit()
    return None


@router.put("/abbreviations/{row_id}/")
async def update_abbreviation(
    row_id: UUID,
    body: AbbreviationUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(RefAbbreviation, row_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.get("/phrases/")
async def list_phrases(
    category: str | None = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    query = select(RefPhrase).order_by(RefPhrase.category, RefPhrase.version.desc())
    if category:
        query = query.where(RefPhrase.category == category)
    if active_only:
        query = query.where(RefPhrase.is_active.is_(True))
    result = await db.execute(query)
    return [
        {
            "id": str(r.id),
            "category": r.category,
            "version": r.version,
            "text": r.text,
            "is_active": r.is_active,
            "effective_from": r.effective_from.isoformat() if r.effective_from else None,
        }
        for r in result.scalars().all()
    ]


@router.post("/phrases/")
async def create_phrase(body: PhraseIn, db: AsyncSession = Depends(get_db)):
    row = RefPhrase(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.put("/phrases/{row_id}/")
async def update_phrase(
    row_id: UUID,
    body: PhraseUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(RefPhrase, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Фраза не найдена")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/phrases/{row_id}/")
async def delete_phrase(row_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(RefPhrase, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Фраза не найдена")
    row.is_active = False
    await db.flush()
    await db.commit()
    return None


@router.post("/phrases/{row_id}/propagate/")
async def propagate_phrase_endpoint(
    row_id: UUID,
    body: PhrasePropagateIn,
    db: AsyncSession = Depends(get_db),
):
    from app.services.phrase_propagate import propagate_phrase

    if body.mode not in {"replace_active", "new_version"}:
        raise HTTPException(status_code=422, detail="mode: replace_active | new_version")
    try:
        result = await propagate_phrase(
            db,
            row_id,
            mode=body.mode,
            new_text=body.new_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/mto/rooms/")
async def list_mto_rooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RefMtoRoom).order_by(RefMtoRoom.code))
    return [
        {"id": str(r.id), "code": r.code, "name": r.name, "equipment": r.equipment}
        for r in result.scalars().all()
    ]


@router.post("/mto/rooms/")
async def create_mto_room(body: MtoRoomIn, db: AsyncSession = Depends(get_db)):
    row = RefMtoRoom(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/mto/rooms/{row_id}/")
async def delete_mto_room(row_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(RefMtoRoom, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Аудитория не найдена")
    await db.delete(row)
    await db.commit()
    return None


@router.put("/mto/rooms/{row_id}/")
async def update_mto_room(
    row_id: UUID,
    body: MtoRoomUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(RefMtoRoom, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Аудитория не найдена")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


class AuthorLoadIn(BaseModel):
    plan_discipline_id: UUID
    author_name: str
    is_shadow: bool = False
    share_percent: float | None = None
    points_per_credit: float | None = None
    fixed_points: float | None = None


class AuthorLoadPatch(BaseModel):
    author_name: str | None = None
    is_shadow: bool | None = None
    share_percent: float | None = None
    points_per_credit: float | None = None
    fixed_points: float | None = None


class PhrasePropagateIn(BaseModel):
    mode: str = "replace_active"  # replace_active | new_version
    new_text: str | None = None


@router.get("/authors-load/")
async def list_authors_load(
    plan_discipline_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.models_tz import AuthorLoad

    query = select(AuthorLoad).order_by(AuthorLoad.author_name)
    if plan_discipline_id:
        query = query.where(AuthorLoad.plan_discipline_id == plan_discipline_id)
    result = await db.execute(query)
    return [
        {
            "id": str(r.id),
            "plan_discipline_id": str(r.plan_discipline_id),
            "author_name": r.author_name,
            "is_shadow": r.is_shadow,
            "share_percent": r.share_percent,
            "points_per_credit": r.points_per_credit,
            "fixed_points": r.fixed_points,
        }
        for r in result.scalars().all()
    ]


@router.post("/authors-load/")
async def create_authors_load(body: AuthorLoadIn, db: AsyncSession = Depends(get_db)):
    from app.models import PlanDiscipline
    from app.models_tz import AuthorLoad

    discipline = await db.get(PlanDiscipline, body.plan_discipline_id)
    if discipline is None:
        raise HTTPException(status_code=404, detail="Дисциплина не найдена")
    row = AuthorLoad(**body.model_dump())
    db.add(row)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.put("/authors-load/{row_id}/")
async def update_authors_load(
    row_id: UUID,
    body: AuthorLoadPatch,
    db: AsyncSession = Depends(get_db),
):
    from app.models_tz import AuthorLoad

    row = await db.get(AuthorLoad, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/authors-load/{row_id}/")
async def delete_authors_load(row_id: UUID, db: AsyncSession = Depends(get_db)):
    from app.models_tz import AuthorLoad

    row = await db.get(AuthorLoad, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    await db.delete(row)
    await db.flush()
    await db.commit()
    return None


@router.get("/layout-templates/")
async def layout_templates_status():
    from app.services.template_manager import list_available_layout_files, layout_dir

    return {
        "layout_dir": str(layout_dir()),
        "templates": await list_available_layout_files(),
    }


@router.post("/layout-templates/reseed/")
async def layout_templates_reseed():
    from app.services.template_manager import seed_layout_templates

    registered = await seed_layout_templates()
    return {"registered": registered}
