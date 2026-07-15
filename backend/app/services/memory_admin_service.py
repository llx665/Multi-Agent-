"""Administrative service for inspecting and managing persisted user memory."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.audit_log_service import AuditLogService
from app.services.auth_service import auth_service
from core.logger import LoggerManager
from core.session_context import session_context_manager
from tools.rag.context_engineering import LongTermMemoryManager

logger = LoggerManager.get_logger("memory_admin")


class MemoryAdminService:
    def __init__(self) -> None:
        self.reconfigure()

    @staticmethod
    def _project_root() -> str:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    def reconfigure(
        self,
        context_storage_path: Optional[str] = None,
        long_term_storage_path: Optional[str] = None,
        audit_storage_path: Optional[str] = None,
    ) -> None:
        project_root = self._project_root()
        self.context_storage_path = context_storage_path or os.path.join(project_root, "data", "memory", "session_context")
        os.makedirs(self.context_storage_path, exist_ok=True)
        self.long_term_memory = LongTermMemoryManager(
            storage_path=long_term_storage_path or os.path.join(project_root, "data", "memory", "long_term")
        )
        self.audit_log_service = AuditLogService(
            storage_path=audit_storage_path or os.path.join(project_root, "logs", "admin_audit.jsonl")
        )

    def _context_path(self, user_id: str) -> str:
        return os.path.join(self.context_storage_path, f"{user_id}_context.json")

    def _profile_path(self, user_id: str) -> str:
        return os.path.join(self.long_term_memory.storage_path, f"{user_id}_profile.json")

    @staticmethod
    def _read_json(path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning(f"[MemoryAdmin] failed to read {path}: {exc}")
            return None

    @staticmethod
    def _write_json(path: str, payload: Dict[str, Any]) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            logger.error(f"[MemoryAdmin] failed to write {path}: {exc}")
            return False

    def _list_user_ids_from_dir(self, directory: str, suffix: str) -> List[str]:
        if not os.path.exists(directory):
            return []

        user_ids: List[str] = []
        for filename in os.listdir(directory):
            if filename.endswith(suffix):
                user_ids.append(filename[: -len(suffix)])
        return user_ids

    def _load_context_snapshot(self, user_id: str) -> Dict[str, Any]:
        active_context = session_context_manager.get_session_by_user(user_id)
        if active_context is not None:
            return active_context.get_persistent_snapshot()
        return self._read_json(self._context_path(user_id)) or {}

    def _load_long_term_profile(self, user_id: str) -> Dict[str, Any]:
        return self._read_json(self._profile_path(user_id)) or {}

    def _load_username(self, user_id: str) -> Optional[str]:
        try:
            user = auth_service.get_user_by_id(user_id)
        except Exception as exc:
            logger.warning(f"[MemoryAdmin] failed to load username for {user_id}: {exc}")
            return None

        if not user:
            return None
        return user.get("username")

    @staticmethod
    def _matches_query(record: Dict[str, Any], query: str) -> bool:
        keyword = query.strip().lower()
        if not keyword:
            return True
        return keyword in (record.get("user_id") or "").lower() or keyword in (record.get("username") or "").lower()

    def list_users(self, query: Optional[str] = None, active_only: Optional[bool] = None) -> List[Dict[str, Any]]:
        user_ids = set(session_context_manager.list_user_ids())
        user_ids.update(self._list_user_ids_from_dir(self.context_storage_path, "_context.json"))
        user_ids.update(self._list_user_ids_from_dir(self.long_term_memory.storage_path, "_profile.json"))

        users: List[Dict[str, Any]] = []
        for user_id in sorted(user_ids):
            context_snapshot = self._load_context_snapshot(user_id)
            long_term_profile = self._load_long_term_profile(user_id)
            summary = context_snapshot.get("three_tier_summary") or {}
            username = self._load_username(user_id)
            users.append(
                {
                    "user_id": user_id,
                    "username": username,
                    "active_in_memory": session_context_manager.get_session_by_user(user_id) is not None,
                    "session_id": context_snapshot.get("session_id"),
                    "last_updated": context_snapshot.get("updated_at") or long_term_profile.get("last_updated"),
                    "total_turns": len(context_snapshot.get("turn_history") or []),
                    "short_term_turns": summary.get("stats", {}).get("short_term_turns", 0),
                    "medium_term_count": summary.get("stats", {}).get("compressed_memories", 0),
                    "preference_count": len((long_term_profile.get("preferences") or {}).keys()),
                }
            )
        if query:
            users = [user for user in users if self._matches_query(user, query)]
        if active_only is not None:
            users = [user for user in users if user["active_in_memory"] is active_only]
        return users

    def get_user_details(self, user_id: str) -> Dict[str, Any]:
        context_snapshot = self._load_context_snapshot(user_id)
        long_term_profile = self._load_long_term_profile(user_id)
        return {
            "user_id": user_id,
            "username": self._load_username(user_id),
            "active_in_memory": session_context_manager.get_session_by_user(user_id) is not None,
            "context_snapshot": context_snapshot,
            "long_term_profile": long_term_profile,
        }

    def _write_audit(
        self,
        actor_id: Optional[str],
        action: str,
        user_id: str,
        result: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not actor_id:
            return
        self.audit_log_service.write(
            actor_id=actor_id,
            module="memory",
            action=action,
            target_type="user_memory",
            target_id=user_id,
            result=result,
            extra=extra,
        )

    def update_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        confidence: float = 1.0,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.long_term_memory.update_preference(
            user_id=user_id,
            key=key,
            value=value,
            source="admin_override",
            confidence=confidence,
        )
        self.long_term_memory.save_profile(user_id)

        active_context = session_context_manager.get_session_by_user(user_id)
        if active_context is not None:
            active_context.metadata[key] = value
            active_context.persist_long_term_memory()
        else:
            context_snapshot = self._load_context_snapshot(user_id)
            if context_snapshot:
                metadata = context_snapshot.setdefault("metadata", {})
                metadata[key] = value
                context_snapshot["updated_at"] = datetime.now().isoformat()
                self._write_json(self._context_path(user_id), context_snapshot)

        details = self.get_user_details(user_id)
        self._write_audit(
            actor_id=actor_id,
            action="update_preference",
            user_id=user_id,
            result="success",
            extra={"key": key, "confidence": confidence},
        )
        return details

    def clear_user_context(self, user_id: str, actor_id: Optional[str] = None) -> bool:
        active_context = session_context_manager.get_session_by_user(user_id)
        if active_context is not None:
            success = session_context_manager.delete_session(
                active_context.session_id,
                user_id=user_id,
                remove_persisted=True,
            )
            self._write_audit(actor_id=actor_id, action="clear_context", user_id=user_id, result="success" if success else "failed")
            return success

        path = self._context_path(user_id)
        success = True
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                logger.error(f"[MemoryAdmin] failed to remove context for {user_id}: {exc}")
                success = False
        self._write_audit(actor_id=actor_id, action="clear_context", user_id=user_id, result="success" if success else "failed")
        return success

    def clear_user_all_memory(self, user_id: str, actor_id: Optional[str] = None) -> bool:
        context_cleared = self.clear_user_context(user_id)

        self.long_term_memory.user_profiles.pop(user_id, None)
        profile_path = self._profile_path(user_id)
        profile_cleared = True
        if os.path.exists(profile_path):
            try:
                os.remove(profile_path)
            except OSError as exc:
                logger.error(f"[MemoryAdmin] failed to remove profile for {user_id}: {exc}")
                profile_cleared = False

        success = context_cleared and profile_cleared
        self._write_audit(actor_id=actor_id, action="clear_all", user_id=user_id, result="success" if success else "failed")
        return success


memory_admin_service = MemoryAdminService()
