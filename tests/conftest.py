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
    import app.models_tz  # noqa: F401

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
            "ALTER TABLE study_plans ADD COLUMN IF NOT EXISTS folder_path VARCHAR",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS program_kind VARCHAR(16) DEFAULT 'discipline'",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE",
            "ALTER TABLE programs ADD COLUMN IF NOT EXISTS constructor_json TEXT",
            "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS cycle_identifier VARCHAR(32)",
            "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS block_type VARCHAR(32)",
            "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS block_code VARCHAR(16)",
            "ALTER TABLE archive_volume_items ADD COLUMN IF NOT EXISTS page_start INTEGER",
            "ALTER TABLE archive_volume_items ADD COLUMN IF NOT EXISTS page_end INTEGER",
            "ALTER TABLE program_zuv ADD COLUMN IF NOT EXISTS row_order INTEGER DEFAULT 0",
            "ALTER TABLE program_zuv DROP CONSTRAINT IF EXISTS uq_program_zuv_indicator_type",
            """
            CREATE TABLE IF NOT EXISTS direction_program_library (
                id UUID PRIMARY KEY,
                profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                discipline_code VARCHAR(32) NOT NULL,
                doc_kind VARCHAR(8) NOT NULL,
                document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                content_hash VARCHAR(64) NOT NULL,
                source_filename VARCHAR NOT NULL,
                extract_json TEXT,
                uploaded_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT uq_direction_library_discipline_kind
                    UNIQUE (profile_id, discipline_code, doc_kind)
            )
            """,
        ):
            await conn.execute(text(ddl))

    async with session_factory() as session:
        yield session

    await engine.dispose()
