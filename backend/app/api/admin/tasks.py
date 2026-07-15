from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.admin.dependencies import require_admin_user
from app.services.task_queue_service import task_queue_service

router = APIRouter(prefix="/tasks", tags=["admin-tasks"])


@router.get("")
async def list_tasks(
    status: Optional[str] = Query(default=None),
    user=Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del user
    return {"tasks": task_queue_service.list_tasks(status=status or None)}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    user=Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del user
    task = task_queue_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: str,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    del user
    if not task_queue_service.get_task(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return task_queue_service.retry(task_id)
