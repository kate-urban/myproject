"""Блокировки записей (опционально, EDIT_LOCKS_ENABLED=false по умолчанию)."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EDIT_LOCKS_ENABLED, LOCK_TTL_SECONDS
from app.models import EditLock, Program
from app.services.auth import CurrentUser


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def purge_expired_locks(db: AsyncSession) -> None:
    await db.execute(delete(EditLock).where(EditLock.expires_at < _utcnow()))


async def get_lock(
    db: AsyncSession,
    resource_type: str,
    resource_id: uuid.UUID,
) -> EditLock | None:
    await purge_expired_locks(db)
    result = await db.execute(
        select(EditLock).where(
            EditLock.resource_type == resource_type,
            EditLock.resource_id == resource_id,
        )
    )
    return result.scalar_one_or_none()


async def acquire_lock(
    db: AsyncSession,
    *,
    user: CurrentUser,
    resource_type: str,
    resource_id: uuid.UUID,
) -> tuple[EditLock | None, str | None]:
    if not EDIT_LOCKS_ENABLED:
        return None, None

    await purge_expired_locks(db)
    existing = await get_lock(db, resource_type, resource_id)
    if existing:
        if existing.user_id == user.id:
            existing.expires_at = _utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)
            await db.flush()
            return existing, None
        return None, f"Занято: {existing.user_display_name}"

    lock = EditLock(
        id=uuid.uuid4(),
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user.id,
        user_display_name=user.display_name,
        session_token=secrets.token_urlsafe(24),
        expires_at=_utcnow() + timedelta(seconds=LOCK_TTL_SECONDS),
    )
    db.add(lock)
    await db.flush()
    return lock, None


async def heartbeat_lock(
    db: AsyncSession,
    *,
    token: str,
    user: CurrentUser,
) -> EditLock | None:
    if not EDIT_LOCKS_ENABLED:
        return None

    result = await db.execute(
        select(EditLock).where(EditLock.session_token == token)
    )
    lock = result.scalar_one_or_none()
    if not lock or lock.user_id != user.id:
        return None
    if lock.expires_at < _utcnow():
        await db.delete(lock)
        await db.flush()
        return None
    lock.expires_at = _utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)
    await db.flush()
    return lock


async def release_lock(
    db: AsyncSession,
    *,
    token: str,
    user: CurrentUser,
) -> bool:
    if not EDIT_LOCKS_ENABLED:
        return True

    result = await db.execute(
        select(EditLock).where(EditLock.session_token == token)
    )
    lock = result.scalar_one_or_none()
    if not lock:
        return True
    if lock.user_id != user.id:
        return False
    await db.delete(lock)
    await db.flush()
    return True


async def assert_can_edit_document(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    user: CurrentUser,
    program_id: uuid.UUID | None = None,
) -> None:
    if not EDIT_LOCKS_ENABLED:
        return

    if program_id is not None:
        result = await db.execute(
            select(Program).where(
                Program.id == program_id,
                (Program.document_id == document_id) | (Program.fos_document_id == document_id),
            )
        )
        program = result.scalar_one_or_none()
        if not program:
            return
        lock = await get_lock(db, "program", program.id)
        if lock and lock.user_id != user.id:
            raise PermissionError(f"РПД/ФОС заняты: {lock.user_display_name}")
        return

    result = await db.execute(
        select(Program).where(
            (Program.document_id == document_id) | (Program.fos_document_id == document_id)
        )
    )
    programs = result.scalars().all()
    if not programs:
        return

    for program in programs:
        lock = await get_lock(db, "program", program.id)
        if lock and lock.user_id != user.id:
            raise PermissionError(f"РПД/ФОС заняты: {lock.user_display_name}")


async def locks_for_program_ids(
    db: AsyncSession,
    program_ids: list[uuid.UUID],
) -> dict[uuid.UUID, EditLock]:
    if not EDIT_LOCKS_ENABLED or not program_ids:
        return {}

    await purge_expired_locks(db)
    result = await db.execute(
        select(EditLock).where(
            EditLock.resource_type == "program",
            EditLock.resource_id.in_(program_ids),
        )
    )
    return {lock.resource_id: lock for lock in result.scalars().all()}
