"""Проверка Bearer-токена для /api/v1 при AUTH_ENABLED=true."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.auth_deps import extract_token
from app.config import AUTH_ENABLED
from app.database import AsyncSessionLocal
from app.services.auth import require_user

# Публичные маршруты без токена (только при включённой авторизации)
_PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("GET", "/api/v1/workspace/config"),
    ("GET", "/api/v1/workspace/config/"),
    ("GET", "/api/v1/workspace/auth-status"),
    ("GET", "/api/v1/workspace/auth-status/"),
    ("POST", "/api/v1/workspace/login"),
    ("POST", "/api/v1/workspace/login/"),
    ("POST", "/api/v1/workspace/register"),
    ("POST", "/api/v1/workspace/register/"),
}


def _normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path
    if path.endswith("/"):
        return path
    return f"{path}/"


async def api_auth_middleware(request: Request, call_next):
    if not AUTH_ENABLED:
        return await call_next(request)

    if request.method.upper() == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api/v1"):
        return await call_next(request)

    key = (request.method.upper(), path.rstrip("/") or "/")
    key_slash = (request.method.upper(), _normalize_path(path))
    if key in _PUBLIC_ROUTES or key_slash in _PUBLIC_ROUTES:
        return await call_next(request)

    token = extract_token(request.headers.get("authorization"))
    try:
        async with AsyncSessionLocal() as db:
            await require_user(db, token=token)
    except PermissionError:
        return JSONResponse({"detail": "Требуется вход"}, status_code=401)

    return await call_next(request)
