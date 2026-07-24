"""Render deployment entry point."""
import os, sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1 import auth, chat, skills, health, knowledge_base, evaluation, metrics
from app.api.admin import dashboard, knowledge, memory, settings as admin_settings, tasks, users
from app.config import settings
from core.logger import LoggerManager

LoggerManager.initialize()
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
for p in [str(BACKEND_DIR), str(PROJECT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

@asynccontextmanager
async def lifespan(app):
    print(f"[START] {settings.app_name} on Render")
    frontend_path = PROJECT_DIR / "frontend" / "dist"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    yield
    print("[STOP] Shutting down")

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(chat.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(knowledge_base.router, prefix="/api/v1")
app.include_router(evaluation.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/admin")
app.include_router(dashboard.router, prefix="/api/admin")
app.include_router(users.router, prefix="/api/admin")
app.include_router(knowledge.router, prefix="/api/admin")
app.include_router(admin_settings.router, prefix="/api/admin")
app.include_router(tasks.router, prefix="/api/admin")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.app_name}
