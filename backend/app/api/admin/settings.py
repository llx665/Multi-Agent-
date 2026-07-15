from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.admin.dependencies import require_admin_user
from app.services.settings_admin_service import SettingsAdminValidationError, settings_admin_service

router = APIRouter()


class RuntimeSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_size: int = Field(default=400)
    chunk_overlap: int = Field(default=50)
    top_k: int = Field(default=5)
    similarity_threshold: float = Field(default=0.3)
    enable_cache: bool = True
    enable_rerank: bool = True
    enable_hybrid: bool = True
    enable_self_rag: bool = False


class KnowledgeBasePolicyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    intro_text: str
    empty_state_text: str
    readonly_notice: str
    show_document_metrics: bool


class SettingsSummaryPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    show_summary: bool
    show_runtime_overview: bool
    show_permission_notice: bool
    readonly_notice: str


class FrontendPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    knowledge_base: KnowledgeBasePolicyRequest
    settings: SettingsSummaryPolicyRequest


def _raise_bad_request(exc: Exception) -> None:
    if isinstance(exc, SettingsAdminValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/settings/summary")
async def get_settings_summary(user=Depends(require_admin_user("admin", "super_admin"))):
    del user
    return settings_admin_service.get_summary()


@router.post("/settings/runtime")
async def update_runtime_settings(
    request: RuntimeSettingsRequest,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        params = settings_admin_service.update_runtime_params(request.model_dump(), actor_id=user["id"])
    except Exception as exc:
        _raise_bad_request(exc)
    return {"success": True, "params": params}


@router.post("/settings/frontend-policy")
async def update_frontend_policy(
    request: FrontendPolicyRequest,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        policy = settings_admin_service.update_frontend_policy(request.model_dump(), actor_id=user["id"])
    except Exception as exc:
        _raise_bad_request(exc)
    return {"success": True, "policy": policy}
