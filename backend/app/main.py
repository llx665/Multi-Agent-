"""
FastAPI 主入口
"""
import sys
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.v1 import auth, chat, skills, health, knowledge_base, evaluation, metrics
from app.api.admin import tasks as admin_tasks
from app.config import settings

# 初始化日志系统
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.logger import LoggerManager
LoggerManager.initialize()

# API 级限流器（每 IP 每分钟 30 次，突发射 60 次）
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["30/minute"],
    storage_uri="memory://",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[START] {settings.app_name} 启动")

    # 挂载前端静态文件（如果前端已构建）
    frontend_path = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
        print(f"[MOUNT] 前端静态文件已挂载: {frontend_path}")

    yield
    print(f"[STOP] {settings.app_name} 关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于 LangChain + DeepSeek 的智能客服系统",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(knowledge_base.router, prefix="/api/v1")
app.include_router(evaluation.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(admin_tasks.router, prefix="/api/admin")


@app.get("/")
async def root():
    # 检查前端是否已构建
    frontend_path = Path(__file__).parent.parent.parent / "frontend" / "dist" / "index.html"
    if frontend_path.exists():
        return {"message": "前端已构建，访问 http://localhost:8000 查看", "static": True}
    return {"message": f"🤖 {settings.app_name} 已启动", "version": settings.app_version}
