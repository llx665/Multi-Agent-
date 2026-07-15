from __future__ import annotations

from app.services.audit_log_service import audit_log_service
from app.services.auth_service import AuthError, auth_service


class UserAdminServiceError(Exception):
    """Base error for user admin service."""


class BadRequestError(UserAdminServiceError):
    """400-level validation error."""


class ForbiddenError(UserAdminServiceError):
    """403-level authorization error."""


class NotFoundError(UserAdminServiceError):
    """404-level missing resource error."""


class UserAdminService:
    _MANAGEABLE_BY_ADMIN = {"user", "operator"}

    def list_users(self, query: str = "", role: str = "", status: str = "") -> list[dict]:
        users = auth_service.list_users()
        if query:
            lowered = query.lower()
            users = [
                item
                for item in users
                if lowered in (item.get("username") or "").lower() or lowered in (item.get("id") or "").lower()
            ]
        if role:
            users = [item for item in users if item.get("role") == role]
        if status:
            users = [item for item in users if item.get("status") == status]
        return users

    def _validate_actor_role(self, actor_role: str) -> None:
        if actor_role not in {"admin", "super_admin"}:
            raise ForbiddenError("insufficient permissions")

    def _load_target_user(self, user_id: str) -> dict:
        user = auth_service.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("user not found")
        return user

    @staticmethod
    def _raise_mapped_auth_error(exc: AuthError) -> None:
        if str(exc) == "user not found":
            raise NotFoundError("user not found") from exc
        raise BadRequestError(str(exc)) from exc

    def _ensure_manageable(self, actor_id: str, actor_role: str, target_user: dict, operation: str) -> None:
        self._validate_actor_role(actor_role)
        if operation == "status":
            if actor_id == target_user.get("id"):
                raise ForbiddenError("cannot update own status")
            if actor_role == "admin" and target_user.get("role") not in self._MANAGEABLE_BY_ADMIN:
                raise ForbiddenError("admin can only manage user/operator")
        if operation == "role":
            if actor_role == "admin":
                raise ForbiddenError("admin cannot modify role")
            if actor_role == "super_admin" and actor_id == target_user.get("id"):
                raise ForbiddenError("super_admin cannot modify own role")

    def get_user_detail(self, actor_role: str, user_id: str) -> dict:
        self._validate_actor_role(actor_role)
        target = self._load_target_user(user_id)
        return {
            "id": target.get("id"),
            "username": target.get("username"),
            "role": target.get("role"),
            "status": target.get("status"),
            "created_at": target.get("created_at"),
            "updated_at": target.get("updated_at"),
            "last_login_at": target.get("last_login_at"),
            "password_updated_at": target.get("password_updated_at"),
        }

    def update_status(self, actor_id: str, actor_role: str, user_id: str, status: str) -> dict:
        if status not in {"active", "disabled"}:
            raise BadRequestError("unsupported status")

        target = self._load_target_user(user_id)
        self._ensure_manageable(actor_id, actor_role, target, operation="status")
        old_status = target.get("status")
        try:
            updated = auth_service.update_user_status(user_id, status)
        except AuthError as exc:
            self._raise_mapped_auth_error(exc)

        audit_log_service.write(
            actor_id=actor_id,
            module="users",
            action="update_status",
            target_type="user",
            target_id=user_id,
            result="success",
            extra={"old_status": old_status, "new_status": updated.get("status")},
        )
        return updated

    def update_role(self, actor_id: str, actor_role: str, user_id: str, role: str) -> dict:
        if not user_id or not role:
            raise BadRequestError("user id and role are required")
        if role not in {"user", "operator", "admin", "super_admin"}:
            raise BadRequestError("unsupported role")

        target = self._load_target_user(user_id)
        self._ensure_manageable(actor_id, actor_role, target, operation="role")
        old_role = target.get("role")
        try:
            updated = auth_service.update_user_role(user_id, role)
        except AuthError as exc:
            self._raise_mapped_auth_error(exc)

        audit_log_service.write(
            actor_id=actor_id,
            module="users",
            action="update_role",
            target_type="user",
            target_id=user_id,
            result="success",
            extra={"old_role": old_role, "new_role": updated.get("role")},
        )
        return updated


user_admin_service = UserAdminService()
