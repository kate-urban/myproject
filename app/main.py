from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router
from app.api.study_plans import router as study_plans_router
from app.api.workspace import router as workspace_router
from app.api.reference import router as reference_router
from app.api.reports import router as reports_router
from app.api.archive import router as archive_router
from app.api.development import router as development_router
from app.api.program_constructor import router as program_constructor_router
from app.api.reapproval import router as reapproval_router
from app.api.direction_library import router as direction_library_router
from app.api.assist import router as assist_router
from app.api.program_p3 import router as program_p3_router
from app.api.program_content import router as program_content_router
from app.database import engine, Base, AsyncSessionLocal
from app.services.template_manager import seed_layout_templates

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITOR_PATH = os.path.join(BASE_DIR, "index.html")
WORKSPACE_PATH = os.path.join(BASE_DIR, "workspace.html")
VALIDATION_PATH = os.path.join(BASE_DIR, "validation.html")
REFERENCE_PATH = os.path.join(BASE_DIR, "reference.html")
STATIC_DIR = os.path.join(BASE_DIR, "static")

if "TEMPLATES_DIR" not in os.environ:
    os.environ["TEMPLATES_DIR"] = os.path.join(BASE_DIR, "templates")
if "LAYOUT_DIR" not in os.environ:
    os.environ["LAYOUT_DIR"] = os.path.join(BASE_DIR, "Layout")

TEMPLATES_DIR = os.environ["TEMPLATES_DIR"]
EXPORTS_DIR = os.getenv("EXPORTS_DIR", os.path.join(BASE_DIR, "exports"))

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

from app.middleware.api_auth import api_auth_middleware
from app.services.signature_storage import signatures_dir  # noqa: E402

os.makedirs(signatures_dir(), exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text

    from app.services.auth import cleanup_placeholder_users, seed_admin_users
    from app.services.reference_seed import seed_reference_defaults
    from app.services.signature_storage import migrate_legacy_signatures

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
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_path VARCHAR")
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
        await conn.execute(
            text(
                "ALTER TABLE study_plans ADD COLUMN IF NOT EXISTS folder_path VARCHAR"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS program_kind VARCHAR(16) DEFAULT 'discipline'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS constructor_json TEXT"
            )
        )
        for ddl in (
            "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS cycle_identifier VARCHAR(32)",
            "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS block_type VARCHAR(32)",
            "ALTER TABLE plan_disciplines ADD COLUMN IF NOT EXISTS block_code VARCHAR(16)",
            "ALTER TABLE archive_volumes ADD COLUMN IF NOT EXISTS duplex_enabled BOOLEAN DEFAULT TRUE",
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

    async with AsyncSessionLocal() as session:
        await cleanup_placeholder_users(session)
        await seed_admin_users(session)
        await seed_reference_defaults(session)
        await migrate_legacy_signatures(session)
        await session.commit()

    from app.services.export_cleanup import cleanup_exports_directory
    from app.services.layout_bootstrap import ensure_layout_files

    ensure_layout_files()
    await seed_layout_templates()

    cleanup_exports_directory(EXPORTS_DIR)

    import asyncio

    from app.config import plans_auto_import
    from app.services.plans_folder_nav import sync_folder_plans

    async def _startup_plan_sync() -> None:
        if not plans_auto_import():
            return
        try:
            async with AsyncSessionLocal() as session:
                await sync_folder_plans(session)
                await session.commit()
        except Exception:
            pass

    asyncio.create_task(_startup_plan_sync())
    yield


app = FastAPI(title="УМУ — учебные планы и РПД", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_private_assets(request: Request, call_next):
    path = request.url.path.replace("\\", "/").lower()
    blocked_prefixes = (
        "/static/signatures",
        "/static/signatures/",
        "/data/private",
        "/data/private/",
        "/exports",
        "/exports/",
    )
    from app.config import AUTH_ENABLED

    if AUTH_ENABLED:
        blocked_prefixes = blocked_prefixes + (
            "/templates",
            "/templates/",
        )
    if any(path == prefix or path.startswith(prefix) for prefix in blocked_prefixes):
        return JSONResponse({"detail": "Доступ запрещён"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.middleware("http")
async def enforce_api_auth(request: Request, call_next):
    return await api_auth_middleware(request, call_next)


app.include_router(router, prefix="/api/v1")
app.include_router(study_plans_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(reference_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(archive_router, prefix="/api/v1")
app.include_router(development_router, prefix="/api/v1")
app.include_router(program_constructor_router, prefix="/api/v1")
app.include_router(reapproval_router, prefix="/api/v1")
app.include_router(program_content_router, prefix="/api/v1")
app.include_router(program_p3_router, prefix="/api/v1")
app.include_router(direction_library_router, prefix="/api/v1")
app.include_router(assist_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse)
async def root():
    if not os.path.exists(WORKSPACE_PATH):
        return HTMLResponse(
            "<h1>Файл workspace.html не найден</h1>",
            status_code=404,
        )
    return FileResponse(
        WORKSPACE_PATH,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/editor", response_class=HTMLResponse)
async def editor_ui():
    if not os.path.exists(EDITOR_PATH):
        return HTMLResponse(
            "<h1>Файл index.html не найден</h1>",
            status_code=404,
        )
    return FileResponse(
        EDITOR_PATH,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/workspace", include_in_schema=False)
@app.get("/workspace/", include_in_schema=False)
async def workspace_redirect():
    return RedirectResponse(url="/", status_code=302)


@app.get("/reference", response_class=HTMLResponse)
async def reference_ui():
    if not os.path.exists(REFERENCE_PATH):
        return HTMLResponse(
            "<h1>Файл reference.html не найден</h1>",
            status_code=404,
        )
    return FileResponse(
        REFERENCE_PATH,
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
