"""Authentication API routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.auth_service import AuthError, auth_service
from tools.rag.context_engineering import LongTermMemoryManager

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class ResolveMemoryRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AuthResponse(BaseModel):
    user_id: str
    username: str
    token: str
    expires_at: int


_memory_manager = LongTermMemoryManager()


def _resolve_current_user(authorization: Optional[str]) -> Dict[str, Any]:
    try:
        return auth_service.get_user_from_authorization(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    try:
        user = auth_service.register(request.username, request.password)
        token_data = auth_service.create_token(user_id=user["id"], username=user["username"])
        return AuthResponse(
            user_id=user["id"],
            username=user["username"],
            token=token_data["token"],
            expires_at=token_data["expires_at"],
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    try:
        user = auth_service.authenticate(request.username, request.password)
        token_data = auth_service.create_token(user_id=user["id"], username=user["username"])
        return AuthResponse(
            user_id=user["id"],
            username=user["username"],
            token=token_data["token"],
            expires_at=token_data["expires_at"],
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/auth/me")
async def me(authorization: Optional[str] = Header(default=None)):
    user = _resolve_current_user(authorization)
    return {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "status": user["status"],
        "expires_at": user["exp"],
    }


@router.get("/auth/memory")
async def get_memory_profile(authorization: Optional[str] = Header(default=None)):
    user = _resolve_current_user(authorization)
    profile = _memory_manager.get_or_create_profile(user["id"])

    return {
        "user_id": profile.user_id,
        "preferences": profile.preferences,
        "preference_meta": profile.preference_meta,
        "preference_history": profile.preference_history[-30:],
        "preference_conflicts": profile.preference_conflicts[-30:],
        "discussed_entities": profile.discussed_entities,
        "last_updated": profile.last_updated,
    }


@router.post("/auth/memory/resolve")
async def resolve_memory(
    request: ResolveMemoryRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _resolve_current_user(authorization)

    _memory_manager.update_preference(
        user_id=user["id"],
        key=request.key,
        value=request.value,
        source="explicit_user",
        confidence=request.confidence,
    )
    _memory_manager.save_profile(user["id"])

    profile = _memory_manager.get_or_create_profile(user["id"])
    return {
        "success": True,
        "message": "memory preference resolved",
        "key": request.key,
        "value": profile.preferences.get(request.key),
        "meta": profile.preference_meta.get(request.key, {}),
    }
