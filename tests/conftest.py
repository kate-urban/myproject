"""Фикстуры для интеграционных тестов с PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
SAMPLES = ROOT / "samples"
DESIGN_PLX = SAMPLES / "M540401-2026.plx"
DESIGN_RPD = SAMPLES / "B1_O_01_07_Proektnaya_deyatelnost_k55.docx"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: tests requiring PostgreSQL")


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES


@pytest_asyncio.fixture
async def db_session():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    from app.database import Base
    import app.models  # noqa: F401

    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS hours_aud INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_discipline_code VARCHAR(32)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_hours_total INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_credits DOUBLE PRECISION"
            )
        )
        for ddl in (
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_discipline_name VARCHAR",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_direction_code VARCHAR(16)",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_profile_name VARCHAR",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_department_code VARCHAR(16)",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_competencies TEXT",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS rpd_extract_json TEXT",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS fos_document_id UUID",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS fos_extract_json TEXT",
        ):
            await conn.execute(text(ddl))

    async with session_factory() as session:
        yield session

    await engine.dispose()
