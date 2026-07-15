"""Спринт 1: авторизация API, logout, upload limits, закрытие /exports."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import AUTH_ENABLED
from app.main import app
from app.services.auth import hash_password, login, register_user


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr("app.config.AUTH_ENABLED", True)
    monkeypatch.setattr("app.services.auth.AUTH_ENABLED", True)
    monkeypatch.setattr("app.middleware.api_auth.AUTH_ENABLED", True)
    monkeypatch.setattr("app.config.ALLOW_SELF_REGISTRATION", True)
    monkeypatch.setattr("app.services.auth.ALLOW_SELF_REGISTRATION", True)


@pytest.mark.asyncio
async def test_api_requires_auth_when_enabled(auth_enabled, db_session) -> None:
    user, token = await register_user(
        db_session,
        username="secuser1",
        display_name="Security User",
        password="secret12",
    )
    await db_session.commit()
    assert token

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/study-plans/")
        assert res.status_code == 401

        res = await client.get(
            "/api/v1/study-plans/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

        res = await client.get("/api/v1/workspace/config/")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_logout_invalidates_token(auth_enabled, db_session) -> None:
    _, token = await register_user(
        db_session,
        username="secuser2",
        display_name="Logout User",
        password="secret12",
    )
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        res = await client.post("/api/v1/workspace/logout/", headers=headers)
        assert res.status_code == 200

        res = await client.get("/api/v1/study-plans/", headers=headers)
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_exports_path_blocked() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/exports/test.docx")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_upload_limit(auth_enabled, db_session, monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setattr("app.config.max_upload_bytes", lambda: 1024)

    _, token = await register_user(
        db_session,
        username="upluser1",
        display_name="Upload User",
        password="secret12",
    )
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        big = b"x" * 2048
        res = await client.post(
            "/api/v1/upload/",
            headers=headers,
            files={"file": ("big.docx", big, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert res.status_code == 413


def test_bcrypt_password_hash() -> None:
    hashed = hash_password("secret12")
    assert hashed.startswith("$2")
    from app.services.auth import verify_password

    assert verify_password("secret12", hashed)
    assert not verify_password("wrong", hashed)


def test_legacy_sha256_password_still_valid() -> None:
    from app.services.auth import _legacy_hash_password, verify_password

    legacy = _legacy_hash_password("oldpass")
    assert verify_password("oldpass", legacy)


@pytest.mark.asyncio
async def test_resolve_user_requires_token_when_auth_enabled(auth_enabled, db_session) -> None:
    from app.services.auth import resolve_user

    with pytest.raises(PermissionError):
        await resolve_user(db_session, token=None)
