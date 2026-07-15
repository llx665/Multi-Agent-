from __future__ import annotations

from fastapi import Header, HTTPException

from app.services.auth_service import AuthError, auth_service
from app.services.permission_service import PermissionDenied, permission_service


def require_authenticated_user():
    async def dependency(authorization: str | None = Header(default=None)):
        try:
            user = auth_service.get_user_from_authorization(authorization)
            permission_service.require_any_role(user, {"user", "operator", "admin", "super_admin"})
            return user
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except PermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return dependency


def require_admin_user(*allowed_roles: str):
    async def dependency(authorization: str | None = Header(default=None)):
        try:
            user = auth_service.get_user_from_authorization(authorization)
            permission_service.require_any_role(user, set(allowed_roles))
            return user
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except PermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return dependency
