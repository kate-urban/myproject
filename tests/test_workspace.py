"""Тесты целевого рабочего места (additive, флаги по умолчанию выключены)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import AdminUser, EditLock, PlanDiscipline, Program
from app.services.auth import CurrentUser, ensure_default_admin, hash_password, register_user, resolve_user
from app.services.edit_lock import acquire_lock, assert_can_edit_document, release_lock
from app.services.importers import StudyPlanImporter
from app.services.workspace_nav import build_workspace_tree, classify_discipline_bucket

DESIGN_PLX = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "samples"
    / "M540401-2026.plx"
)


def test_classify_practice_by_code() -> None:
    d = PlanDiscipline(code="Б2.О.03(П)", name="Практика")
    assert classify_discipline_bucket(code=d.code, name=d.name) == "practices"


@pytest.mark.asyncio
async def test_ensure_default_admin(db_session) -> None:
    user = await ensure_default_admin(db_session)
    await db_session.commit()
    assert user.username == "admin"
    result = await db_session.execute(select(AdminUser))
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_resolve_user_without_auth(monkeypatch, db_session) -> None:
    monkeypatch.setattr("app.config.AUTH_ENABLED", False)
    monkeypatch.setattr("app.services.auth.AUTH_ENABLED", False)
    user = await resolve_user(db_session)
    assert user.display_name


@pytest.mark.asyncio
async def test_register_user(monkeypatch, db_session) -> None:
    monkeypatch.setattr("app.config.AUTH_ENABLED", True)
    monkeypatch.setattr("app.services.auth.AUTH_ENABLED", True)
    monkeypatch.setattr("app.config.ALLOW_SELF_REGISTRATION", True)
    monkeypatch.setattr("app.services.auth.ALLOW_SELF_REGISTRATION", True)

    user, token = await register_user(
        db_session,
        username="testuser1",
        display_name="Тестов Т.Т.",
        password="secret12",
    )
    assert user.username == "testuser1"
    assert token


@pytest.mark.asyncio
@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="sample plx missing")
async def test_workspace_tree(db_session) -> None:
    importer = StudyPlanImporter()
    await importer.import_file(DESIGN_PLX, db_session)
    await db_session.commit()
    tree = await build_workspace_tree(db_session)
    assert tree
    assert tree[0].directions


@pytest.mark.asyncio
async def test_edit_lock_conflict(monkeypatch, db_session) -> None:
    monkeypatch.setattr("app.services.edit_lock.EDIT_LOCKS_ENABLED", True)

    user1 = AdminUser(
        id=uuid.uuid4(),
        username="u1",
        display_name="Иванова",
        password_hash=hash_password("x"),
    )
    user2 = AdminUser(
        id=uuid.uuid4(),
        username="u2",
        display_name="Петрова",
        password_hash=hash_password("y"),
    )
    db_session.add_all([user1, user2])
    await db_session.flush()

    resource_id = uuid.uuid4()
    lock, err = await acquire_lock(
        db_session,
        user=CurrentUser(id=user1.id, username="u1", display_name="Иванова"),
        resource_type="program",
        resource_id=resource_id,
    )
    assert lock and not err

    _, err2 = await acquire_lock(
        db_session,
        user=CurrentUser(id=user2.id, username="u2", display_name="Петрова"),
        resource_type="program",
        resource_id=resource_id,
    )
    assert err2 and "Иванова" in err2


@pytest.mark.asyncio
@pytest.mark.skipif(not DESIGN_PLX.is_file(), reason="sample plx missing")
async def test_assert_can_edit_document_blocked(monkeypatch, db_session) -> None:
    monkeypatch.setattr("app.services.edit_lock.EDIT_LOCKS_ENABLED", True)

    from app.models import Document

    importer = StudyPlanImporter()
    plan = await importer.import_file(DESIGN_PLX, db_session)
    disc = (
        await db_session.execute(
            select(PlanDiscipline)
            .where(PlanDiscipline.study_plan_id == plan.id)
            .limit(1)
            .options(selectinload(PlanDiscipline.program))
        )
    ).scalar_one()

    user1 = AdminUser(id=uuid.uuid4(), username="u1", display_name="Иванова")
    user2 = AdminUser(id=uuid.uuid4(), username="u2", display_name="Петрова")
    doc_id = uuid.uuid4()
    db_session.add_all([user1, user2, Document(id=doc_id, filename="t.docx", doc_type="rpd")])
    await db_session.flush()

    program = disc.program
    if program is None:
        program = Program(
            id=uuid.uuid4(),
            plan_discipline_id=disc.id,
            document_id=doc_id,
            status="linked",
        )
        db_session.add(program)
    else:
        program.document_id = doc_id
    await db_session.flush()

    lock = EditLock(
        id=uuid.uuid4(),
        resource_type="program",
        resource_id=program.id,
        user_id=user1.id,
        user_display_name="Иванова",
        session_token="tok",
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        + __import__("datetime").timedelta(hours=1),
    )
    db_session.add(lock)
    await db_session.flush()

    with pytest.raises(PermissionError, match="Иванова"):
        await assert_can_edit_document(
            db_session,
            document_id=doc_id,
            user=CurrentUser(id=user2.id, username="u2", display_name="Петрова"),
        )

    await release_lock(
        db_session,
        token="tok",
        user=CurrentUser(id=user1.id, username="u1", display_name="Иванова"),
    )
