"""API рабочего места и авторизации."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    AUTH_ENABLED,
    ALLOW_SELF_REGISTRATION,
    EDIT_LOCKS_ENABLED,
    MAX_ADMIN_USERS,
    STRUCTURED_RPD_ENABLED,
    ai_assistant_enabled,
    ai_llm_configured,
    plans_auto_import,
    plans_delete_after_import,
)
from app.database import get_db
from app.workspace_schemas import (
    AcquireLockIn,
    AdminUserOut,
    AuthStatusOut,
    EditLockOut,
    LockStatusOut,
    LoginIn,
    LoginOut,
    RegisterIn,
    WorkspaceConfigOut,
    WorkspaceYearOut,
)
from app.api.auth_deps import extract_token, get_current_user
from app.services.auth import (
    CurrentUser,
    count_active_users,
    login,
    logout,
    register_user,
    require_user,
    resolve_user,
    user_from_token,
)
from app.services.edit_lock import acquire_lock, get_lock, heartbeat_lock, release_lock
from app.services.workspace_nav import build_workspace_tree

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/", include_in_schema=False)
async def workspace_api_root():
    return RedirectResponse(url="/", status_code=302)


def _lock_out(lock) -> EditLockOut:
    return EditLockOut(
        id=lock.id,
        resource_type=lock.resource_type,
        resource_id=lock.resource_id,
        user_display_name=lock.user_display_name,
        acquired_at=lock.acquired_at,
        expires_at=lock.expires_at,
        token=lock.session_token,
    )


@router.get("/config/", response_model=WorkspaceConfigOut)
async def workspace_config():
    return WorkspaceConfigOut(
        auth_enabled=AUTH_ENABLED,
        edit_locks_enabled=EDIT_LOCKS_ENABLED,
        structured_rpd_enabled=STRUCTURED_RPD_ENABLED,
        plans_auto_import=plans_auto_import(),
        plans_delete_after_import=plans_delete_after_import(),
        legacy_editor_url="/editor",
        legacy_validation_url="/validation",
        ai_assistant_enabled=ai_assistant_enabled(),
        ai_llm_configured=ai_llm_configured(),
    )


@router.get("/auth-status/", response_model=AuthStatusOut)
async def auth_status(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None, alias="Authorization"),
):
    token = extract_token(authorization)
    users_count = await count_active_users(db)
    user = await user_from_token(db, token)
    can_register = (
        AUTH_ENABLED
        and users_count < MAX_ADMIN_USERS
        and (ALLOW_SELF_REGISTRATION or users_count == 0)
    )
    return AuthStatusOut(
        auth_enabled=AUTH_ENABLED,
        authenticated=user is not None or not AUTH_ENABLED,
        can_register=can_register,
        users_count=users_count,
        max_users=MAX_ADMIN_USERS,
        user=AdminUserOut.model_validate(user) if user else None,
    )


@router.get("/me/", response_model=AdminUserOut)
async def current_user(user: CurrentUser = Depends(get_current_user)):
    return AdminUserOut(id=user.id, username=user.username, display_name=user.display_name)


@router.post("/register/", response_model=LoginOut)
async def workspace_register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await register_user(
            db,
            username=body.username,
            display_name=body.display_name,
            password=body.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return LoginOut(user=AdminUserOut.model_validate(user), token=token)


@router.post("/login/", response_model=LoginOut)
async def workspace_login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    if not AUTH_ENABLED:
        user_ctx = await resolve_user(db)
        from sqlalchemy import select

        from app.models import AdminUser

        result = await db.execute(select(AdminUser).where(AdminUser.id == user_ctx.id))
        user = result.scalar_one()
        return LoginOut(
            user=AdminUserOut.model_validate(user),
            token="auth-disabled",
        )

    result = await login(db, body.username, body.password)
    if not result:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    user, token = result
    await db.commit()
    return LoginOut(user=AdminUserOut.model_validate(user), token=token)


@router.post("/logout/")
async def workspace_logout(
    authorization: str | None = Header(None, alias="Authorization"),
):
    logout(extract_token(authorization))
    return {"ok": True}


@router.get("/tree/", response_model=list[WorkspaceYearOut])
async def workspace_tree(
    include_disciplines: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Лёгкое дерево планов (без дисциплин). include_disciplines=true — тяжёлый режим."""
    return await build_workspace_tree(db, include_disciplines=include_disciplines)


@router.get("/locks/{resource_type}/{resource_id}/", response_model=LockStatusOut)
async def lock_status(
    resource_type: str,
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if not EDIT_LOCKS_ENABLED:
        return LockStatusOut(locked=False, can_edit=True)

    lock = await get_lock(db, resource_type, resource_id)
    if not lock:
        return LockStatusOut(locked=False, can_edit=True)
    can_edit = lock.user_id == user.id
    return LockStatusOut(
        locked=True,
        lock=_lock_out(lock),
        can_edit=can_edit,
        message=None if can_edit else f"Занято: {lock.user_display_name}",
    )


@router.post("/locks/", response_model=EditLockOut)
async def lock_acquire(
    body: AcquireLockIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if body.resource_type not in ("program", "document"):
        raise HTTPException(status_code=400, detail="resource_type: program | document")

    lock, error = await acquire_lock(
        db,
        user=user,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    if not lock:
        now = datetime.now(timezone.utc)
        return EditLockOut(
            id=uuid.uuid4(),
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            user_display_name=user.display_name,
            acquired_at=now,
            expires_at=now + timedelta(days=1),
            token="locks-disabled",
        )

    await db.commit()
    return _lock_out(lock)


@router.post("/locks/heartbeat/{token}/", response_model=EditLockOut)
async def lock_heartbeat(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    lock = await heartbeat_lock(db, token=token, user=user)
    if not lock:
        raise HTTPException(status_code=404, detail="Блокировка не найдена или истекла")
    await db.commit()
    return _lock_out(lock)


@router.delete("/locks/{token}/")
async def lock_release(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    ok = await release_lock(db, token=token, user=user)
    if not ok:
        raise HTTPException(status_code=403, detail="Нельзя снять чужую блокировку")
    await db.commit()
    return {"released": True}
