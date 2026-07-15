from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.admin.dependencies import require_admin_user
from app.services.audit_log_service import audit_log_service

router = APIRouter()


@router.get("/dashboard/summary")
async def get_dashboard_summary(user=Depends(require_admin_user("operator", "admin", "super_admin"))):
    audit_log_service.write(
        actor_id=user["id"],
        module="dashboard",
        action="view",
        target_type="summary",
        target_id="root",
        result="success",
    )
    return {
        "current_user": {"id": user["id"], "role": user["role"]},
        "modules": ["memory", "knowledge", "settings", "users"],
    }
