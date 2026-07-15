"""Аутентификация администраторов (методисты УМУ)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AUTH_ENABLED, ALLOW_SELF_REGISTRATION, DEFAULT_ADMIN_USERNAME, MAX_ADMIN_USERS
from app.models import AdminUser

_SESSIONS: dict[str, uuid.UUID] = {}


def hash_password(password: str) -> str:
    salt = "syllabus-admin-v1"
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return hash_password(password) == password_hash


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class CurrentUser:
    id: uuid.UUID
    username: str
    display_name: str


async def count_active_users(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(AdminUser)
        .where(
            AdminUser.is_active.is_(True),
            AdminUser.password_hash.isnot(None),
        )
    )
    return int(result.scalar_one())


async def cleanup_placeholder_users(db: AsyncSession) -> None:
    """Удаляет служебного admin без пароля — он мешает регистрации."""
    if not AUTH_ENABLED:
        return
    from sqlalchemy import delete

    await db.execute(
        delete(AdminUser).where(AdminUser.password_hash.is_(None))
    )
    await db.flush()


async def ensure_default_admin(db: AsyncSession) -> AdminUser:
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == DEFAULT_ADMIN_USERNAME)
    )
    user = result.scalar_one_or_none()
    if user:
        return user
    user = AdminUser(
        id=uuid.uuid4(),
        username=DEFAULT_ADMIN_USERNAME,
        display_name="Администратор",
        password_hash=None,
    )
    db.add(user)
    await db.flush()
    return user


async def seed_admin_users(db: AsyncSession) -> None:
    """Создаёт учётки из .env, если указаны пароли."""
    import os

    if not AUTH_ENABLED:
        await ensure_default_admin(db)
        return

    pairs = (
        (
            os.getenv("ADMIN1_USERNAME", "methodist1"),
            os.getenv("ADMIN1_NAME", "Методист 1"),
            os.getenv("ADMIN1_PASSWORD", ""),
        ),
        (
            os.getenv("ADMIN2_USERNAME", "methodist2"),
            os.getenv("ADMIN2_NAME", "Методист 2"),
            os.getenv("ADMIN2_PASSWORD", ""),
        ),
    )
    for username, display_name, password in pairs:
        if not password:
            continue
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        if result.scalar_one_or_none():
            continue
        db.add(
            AdminUser(
                id=uuid.uuid4(),
                username=username,
                display_name=display_name,
                password_hash=hash_password(password),
            )
        )
    await db.flush()


async def register_user(
    db: AsyncSession,
    *,
    username: str,
    display_name: str,
    password: str,
) -> tuple[AdminUser, str]:
    username = username.strip()
    display_name = display_name.strip()
    if not AUTH_ENABLED:
        raise ValueError("Регистрация отключена")
    if not ALLOW_SELF_REGISTRATION:
        raise ValueError("Самостоятельная регистрация запрещена — используйте учётные записи из .env")
    if len(username) < 3:
        raise ValueError("Логин — не короче 3 символов")
    if len(display_name) < 2:
        raise ValueError("Укажите имя (ФИО)")
    if len(password) < 6:
        raise ValueError("Пароль — не короче 6 символов")
    if await count_active_users(db) >= MAX_ADMIN_USERS:
        raise ValueError(f"Достигнут лимит администраторов ({MAX_ADMIN_USERS})")

    existing = await db.execute(select(AdminUser).where(AdminUser.username == username))
    if existing.scalar_one_or_none():
        raise ValueError("Логин уже занят")

    user = AdminUser(
        id=uuid.uuid4(),
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    token = create_session_token()
    _SESSIONS[token] = user.id
    return user, token


async def login(db: AsyncSession, username: str, password: str) -> tuple[AdminUser, str] | None:
    result = await db.execute(
        select(AdminUser).where(
            AdminUser.username == username.strip(),
            AdminUser.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    token = create_session_token()
    _SESSIONS[token] = user.id
    return user, token


async def user_from_token(db: AsyncSession, token: str | None) -> AdminUser | None:
    if not token or token == "auth-disabled" or token not in _SESSIONS:
        return None
    result = await db.execute(select(AdminUser).where(AdminUser.id == _SESSIONS[token]))
    user = result.scalar_one_or_none()
    if user and user.is_active:
        return user
    return None


async def resolve_user(
    db: AsyncSession,
    *,
    token: str | None = None,
    username: str | None = None,
) -> CurrentUser:
    if not AUTH_ENABLED:
        user = await ensure_default_admin(db)
        return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)

    user = await user_from_token(db, token)
    if user:
        return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)

    if username:
        result = await db.execute(
            select(AdminUser).where(
                AdminUser.username == username,
                AdminUser.is_active.is_(True),
            )
        )
        user = result.scalar_one_or_none()
        if user:
            return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)

    user = await ensure_default_admin(db)
    return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)


async def require_user(
    db: AsyncSession,
    *,
    token: str | None = None,
) -> CurrentUser:
    if not AUTH_ENABLED:
        return await resolve_user(db, token=token)

    user = await user_from_token(db, token)
    if not user:
        raise PermissionError("Требуется вход")
    return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)


def logout(token: str | None) -> None:
    if token and token in _SESSIONS:
        del _SESSIONS[token]
