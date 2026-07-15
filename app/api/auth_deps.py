"""Зависимости FastAPI для проверки входа администратора."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import CurrentUser, require_user


def extract_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None, alias="Authorization"),
) -> CurrentUser:
    token = extract_token(authorization)
    try:
        return await require_user(db, token=token)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
