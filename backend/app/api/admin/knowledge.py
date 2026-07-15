from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.api.admin.dependencies import require_admin_user
from app.services.knowledge_admin_service import KnowledgeConflictError, knowledge_admin_service

router = APIRouter()


class UpdateKnowledgeDocumentRequest(BaseModel):
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    visible_to_frontend: Optional[bool] = None
    published: Optional[bool] = None
    allowed_roles: Optional[List[str]] = None


class RollbackKnowledgeDocumentRequest(BaseModel):
    target_version_id: str
    reason: Optional[str] = None


def _parse_json_list(raw: Optional[str], field_name: str) -> Optional[List[str]]:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a JSON array") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return [str(item).strip() for item in parsed if str(item).strip()]


def _raise_knowledge_http_error(exc: Exception) -> None:
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail="document or version not found") from exc
    if isinstance(exc, FileExistsError):
        raise HTTPException(status_code=409, detail="document already exists") from exc
    if isinstance(exc, KnowledgeConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/knowledge/documents")
async def list_knowledge_documents(
    keyword: Optional[str] = Query(default=None),
    status: str = Query(default="active"),
    published: Optional[bool] = Query(default=None),
    visible_to_frontend: Optional[bool] = Query(default=None),
    user=Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del user
    try:
        return {
            "documents": knowledge_admin_service.list_documents(
                keyword=keyword,
                status=status,
                published=published,
                visible_to_frontend=visible_to_frontend,
            )
        }
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.get("/knowledge/documents/{document_id}")
async def get_knowledge_document(
    document_id: str,
    user=Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del user
    try:
        return knowledge_admin_service.get_document(document_id, include_deleted=True)
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.get("/knowledge/documents/{document_id}/versions")
async def list_knowledge_document_versions(
    document_id: str,
    user=Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del user
    try:
        return knowledge_admin_service.list_document_versions(document_id)
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.get("/knowledge/documents/{document_id}/versions/{version_id}")
async def get_knowledge_document_version(
    document_id: str,
    version_id: str,
    user=Depends(require_admin_user("operator", "admin", "super_admin")),
):
    del user
    try:
        return knowledge_admin_service.get_document_version(document_id, version_id)
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.post("/knowledge/documents")
async def create_knowledge_document(
    file: UploadFile = File(...),
    description: str = Form(""),
    tags: Optional[str] = Form(None),
    allowed_roles: Optional[str] = Form(None),
    published: bool = Form(False),
    visible_to_frontend: bool = Form(False),
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        created = knowledge_admin_service.create_document(
            filename=file.filename or "",
            content=await file.read(),
            actor_id=user["id"],
            description=description,
            tags=_parse_json_list(tags, "tags"),
            published=published,
            visible_to_frontend=visible_to_frontend,
            allowed_roles=_parse_json_list(allowed_roles, "allowed_roles"),
        )
        task = knowledge_admin_service.enqueue_document_index(
            document_id=created["document_id"],
            version_id=created.get("current_version_id"),
            actor_id=user["id"],
        )
        return {**created, "index_task_id": task["task_id"], "index_status": task["status"]}
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.post("/knowledge/documents/{document_id}/replace")
async def replace_knowledge_document(
    document_id: str,
    file: UploadFile = File(...),
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        replaced = knowledge_admin_service.replace_document(
            document_id,
            filename=file.filename or "",
            content=await file.read(),
            actor_id=user["id"],
        )
        task = knowledge_admin_service.enqueue_document_index(
            document_id=replaced["document_id"],
            version_id=replaced.get("current_version_id"),
            actor_id=user["id"],
        )
        return {**replaced, "index_task_id": task["task_id"], "index_status": task["status"]}
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.patch("/knowledge/documents/{document_id}")
async def update_knowledge_document(
    document_id: str,
    request: UpdateKnowledgeDocumentRequest,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        return knowledge_admin_service.update_document_metadata(
            document_id,
            actor_id=user["id"],
            description=request.description,
            tags=request.tags,
            visible_to_frontend=request.visible_to_frontend,
            published=request.published,
            allowed_roles=request.allowed_roles,
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.delete("/knowledge/documents/{document_id}")
async def delete_knowledge_document(
    document_id: str,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        return knowledge_admin_service.delete_document(document_id, actor_id=user["id"])
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.post("/knowledge/documents/{document_id}/restore")
async def restore_knowledge_document(
    document_id: str,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        return knowledge_admin_service.restore_document(document_id, actor_id=user["id"])
    except Exception as exc:
        _raise_knowledge_http_error(exc)


@router.post("/knowledge/documents/{document_id}/rollback")
async def rollback_knowledge_document(
    document_id: str,
    request: RollbackKnowledgeDocumentRequest,
    user=Depends(require_admin_user("admin", "super_admin")),
):
    try:
        rolled = knowledge_admin_service.rollback_document(
            document_id,
            target_version_id=request.target_version_id,
            actor_id=user["id"],
            reason=request.reason,
        )
        return {
            **rolled,
            "target_version_id": request.target_version_id,
            "new_version_id": rolled.get("current_version_id"),
        }
    except Exception as exc:
        _raise_knowledge_http_error(exc)
