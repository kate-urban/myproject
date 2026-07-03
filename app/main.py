from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router
from app.api.study_plans import router as study_plans_router
from app.database import engine, Base
from app.services.template_manager import seed_layout_templates

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
VALIDATION_PATH = os.path.join(BASE_DIR, "validation.html")

if "TEMPLATES_DIR" not in os.environ:
    os.environ["TEMPLATES_DIR"] = os.path.join(BASE_DIR, "templates")
if "LAYOUT_DIR" not in os.environ:
    os.environ["LAYOUT_DIR"] = os.path.join(BASE_DIR, "Layout")

TEMPLATES_DIR = os.environ["TEMPLATES_DIR"]
EXPORTS_DIR = os.getenv("EXPORTS_DIR", os.path.join(BASE_DIR, "exports"))

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE sections ADD COLUMN IF NOT EXISTS parent_id UUID "
                "REFERENCES sections(id) ON DELETE SET NULL"
            )
        )
        await conn.execute(
            text("ALTER TABLE sections ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 1")
        )
        await conn.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type VARCHAR")
        )
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

    await seed_layout_templates()
    yield


app = FastAPI(title="Document Processor API", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(study_plans_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse)
async def root():
    if not os.path.exists(INDEX_PATH):
        return HTMLResponse(
            "<h1>Файл index.html не найден</h1><p>Положите его в корень проекта.</p>",
            status_code=404,
        )
    return FileResponse(
        INDEX_PATH,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/validation", response_class=HTMLResponse)
async def validation_ui():
    if not os.path.exists(VALIDATION_PATH):
        return HTMLResponse(
            "<h1>Файл validation.html не найден</h1>",
            status_code=404,
        )
    return FileResponse(
        VALIDATION_PATH,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")
app.mount("/exports", StaticFiles(directory=EXPORTS_DIR), name="exports")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
