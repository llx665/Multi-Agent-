"""后台管理系统 FastAPI 应用。"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import dashboard, knowledge, memory, settings, tasks, users

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.logger import LoggerManager

LoggerManager.initialize()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[START] 后台管理 API 已启动")
    yield
    print("[STOP] 后台管理 API 已停止")


app = FastAPI(
    title="后台管理 API",
    version="1.0.0",
    description="统一承载记忆管理、知识库管理、设置管理和账号管理的后台接口。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory.router, prefix="/api/admin")
app.include_router(dashboard.router, prefix="/api/admin")
app.include_router(users.router, prefix="/api/admin")
app.include_router(knowledge.router, prefix="/api/admin")
app.include_router(settings.router, prefix="/api/admin")
app.include_router(tasks.router, prefix="/api/admin")


@app.get("/")
async def root():
    return {
        "message": "后台管理 API 正在运行",
        "ui_hint": "请在 http://localhost:5174/admin.html 打开后台管理前端",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
