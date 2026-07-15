"""Сохранение подписей в справочнике."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.api.reference import SignatureIn, SignatureUpdate, create_signature, delete_signature, list_signatures, update_signature
from app.models_tz import RefSignature
from app.services.auth import CurrentUser


@pytest.fixture
def ref_admin() -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), username="test", display_name="Тест")


@pytest.mark.asyncio
async def test_create_signature_persists(db_session, ref_admin) -> None:
    created = await create_signature(
        SignatureIn(role="director", full_name="Иванова А.А."),
        db_session,
        ref_admin,
    )
    sig_id = created["id"]

    listed = await list_signatures(db_session, ref_admin)
    assert any(row["id"] == sig_id and row["full_name"] == "Иванова А.А." for row in listed)

    row = (
        await db_session.execute(select(RefSignature).where(RefSignature.id == sig_id))
    ).scalar_one()
    assert row.role == "director"
    assert row.is_active is True


@pytest.mark.asyncio
async def test_update_signature(db_session, ref_admin) -> None:
    created = await create_signature(
        SignatureIn(role="director", full_name="Старое имя"),
        db_session,
        ref_admin,
    )
    sig_id = created["id"]
    await update_signature(sig_id, SignatureUpdate(full_name="Новое имя"), db_session, ref_admin)
    listed = await list_signatures(db_session, ref_admin)
    row = next(x for x in listed if x["id"] == sig_id)
    assert row["full_name"] == "Новое имя"


@pytest.mark.asyncio
async def test_delete_signature_hides_from_list(db_session, ref_admin) -> None:
    created = await create_signature(
        SignatureIn(role="director", full_name="Удалить меня"),
        db_session,
        ref_admin,
    )
    sig_id = created["id"]
    await delete_signature(sig_id, db_session, ref_admin)

    listed = await list_signatures(db_session, ref_admin)
    assert all(row["id"] != sig_id for row in listed)

    row = (
        await db_session.execute(select(RefSignature).where(RefSignature.id == sig_id))
    ).scalar_one()
    assert row.is_active is False


@pytest.mark.asyncio
async def test_list_signatures_hides_png_path(db_session, ref_admin) -> None:
    created = await create_signature(
        SignatureIn(role="director", full_name="Секрет"),
        db_session,
        ref_admin,
    )
    row = await db_session.get(RefSignature, created["id"])
    row.png_path = "private/signatures/test.png"
    await db_session.flush()

    listed = await list_signatures(db_session, ref_admin)
    item = next(x for x in listed if x["id"] == created["id"])
    assert item["has_png"] is True
    assert "png_path" not in item
