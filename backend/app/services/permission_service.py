from __future__ import annotations


class PermissionDenied(Exception):
    """Raised when a user lacks the required role or account status."""


class PermissionService:
    def require_any_role(self, user: dict, allowed_roles: set[str]) -> None:
        if not user or user.get("status") != "active":
            raise PermissionDenied("account is not active")
        if user.get("role") not in allowed_roles:
            raise PermissionDenied("insufficient role")


permission_service = PermissionService()
