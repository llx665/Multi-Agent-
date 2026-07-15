from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.admin.dependencies import require_admin_user
from app.services.user_admin_service import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    user_admin_service,
)

router = APIRouter()


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(...)


class UpdateUserStatusRequest(BaseModel):
    status: str = Field(...)


def _raise_http_from_service_error(exc: Exception) -> None:
    if isinstance(exc, BadRequestError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ForbiddenError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise exc


@router.get("/users")
async def list_users(
    q: str = "",
    role: str = "",
    status: str = "",
    user=Depends(require_admin_user("admin", "super_admin")),
):
    items = user_admin_service.list_users(query=q, role=role, status=status)
    return {
        "users": [
            {
                "user_id": item["id"],
                "username": item["username"],
                "role": item["role"],
                "status": item["status"],
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
            for item in items
        ]
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        detail = user_admin_service.get_user_detail(user["role"], user_id)
    except Exception as exc:
        _raise_http_from_service_error(exc)

    return {
        "user_id": detail["id"],
        "username": detail["username"],
        "role": detail["role"],
        "status": detail["status"],
        "created_at": detail.get("created_at"),
        "updated_at": detail.get("updated_at"),
        "last_login_at": detail.get("last_login_at"),
        "password_updated_at": detail.get("password_updated_at"),
    }


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    request: UpdateUserStatusRequest,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        updated = user_admin_service.update_status(
            actor_id=user["id"],
            actor_role=user["role"],
            user_id=user_id,
            status=request.status,
        )
    except Exception as exc:
        _raise_http_from_service_error(exc)

    return {"user_id": updated["id"], "status": updated["status"]}


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: UpdateUserRoleRequest,
    user=Depends(require_admin_user("super_admin")),
):
    try:
        updated = user_admin_service.update_role(
            actor_id=user["id"],
            actor_role=user["role"],
            user_id=user_id,
            role=request.role,
        )
    except Exception as exc:
        _raise_http_from_service_error(exc)

    return {"user_id": updated["id"], "role": updated["role"]}
