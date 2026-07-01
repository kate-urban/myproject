from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router
from app.database import engine, Base

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "./templates")
EXPORTS_DIR = os.getenv("EXPORTS_DIR", "./exports")

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


app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")
app.mount("/exports", StaticFiles(directory=EXPORTS_DIR), name="exports")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
