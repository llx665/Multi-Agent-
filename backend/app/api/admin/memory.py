"""记忆管理后台 API 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.admin.dependencies import require_admin_user
from app.services.memory_admin_service import memory_admin_service

router = APIRouter()


class PreferenceUpdateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.get("/memory/users")
async def list_memory_users(
    query: str | None = Query(default=None, max_length=128),
    active_only: bool | None = Query(default=None),
    current_user: dict = Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del current_user
    users = memory_admin_service.list_users(query=query, active_only=active_only)
    return {"users": users, "count": len(users)}


@router.get("/memory/users/{user_id}")
async def get_memory_user(
    user_id: str,
    current_user: dict = Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del current_user
    details = memory_admin_service.get_user_details(user_id)
    if not details.get("context_snapshot") and not details.get("long_term_profile"):
        raise HTTPException(status_code=404, detail="未找到该用户的记忆数据")
    return details


@router.post("/memory/users/{user_id}/preferences")
async def update_memory_preference(
    user_id: str,
    request: PreferenceUpdateRequest,
    current_user: dict = Depends(require_admin_user("operator", "admin", "super_admin")),
):
    details = memory_admin_service.update_preference(
        user_id=user_id,
        key=request.key,
        value=request.value,
        confidence=request.confidence,
        actor_id=current_user["id"],
    )
    return {"success": True, "details": details}


@router.delete("/memory/users/{user_id}/context")
async def clear_memory_context(
    user_id: str,
    current_user: dict = Depends(require_admin_user("operator", "admin", "super_admin")),
):
    success = memory_admin_service.clear_user_context(user_id, actor_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=500, detail="清理上下文记忆失败")
    return {"success": True, "user_id": user_id}


@router.delete("/memory/users/{user_id}")
async def clear_memory_all(
    user_id: str,
    current_user: dict = Depends(require_admin_user("operator", "admin", "super_admin")),
):
    success = memory_admin_service.clear_user_all_memory(user_id, actor_id=current_user["id"])
    if not success:
        raise HTTPException(status_code=500, detail="清理全部记忆失败")
    return {"success": True, "user_id": user_id}
