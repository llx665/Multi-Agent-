from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4


TASK_STATUSES = {"queued", "running", "succeeded", "failed", "dead"}


class TaskQueueService:
    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path = storage_path
        self._lock = RLock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._idempotency_index: Dict[str, str] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    def enqueue(
        self,
        *,
        task_type: str,
        payload: Dict[str, Any],
        actor_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency_index:
                return dict(self._tasks[self._idempotency_index[idempotency_key]])

            task_id = f"task_{uuid4().hex}"
            now = self._now()
            task = {
                "task_id": task_id,
                "task_type": task_type,
                "payload": dict(payload or {}),
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "status": "queued",
                "attempts": 0,
                "max_attempts": int(max_attempts),
                "error": None,
                "result": None,
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
            }
            self._tasks[task_id] = task
            if idempotency_key:
                self._idempotency_index[idempotency_key] = task_id
            return dict(task)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [task for task in tasks if task["status"] == status]
            return [dict(task) for task in tasks]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def claim_next(self, task_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        allowed = set(task_types or [])
        with self._lock:
            for task in self._tasks.values():
                if task["status"] != "queued":
                    continue
                if allowed and task["task_type"] not in allowed:
                    continue
                now = self._now()
                task["status"] = "running"
                task["attempts"] += 1
                task["started_at"] = now
                task["finished_at"] = None
                task["updated_at"] = now
                return dict(task)
        return None

    def complete(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            task = self._tasks[task_id]
            now = self._now()
            task["status"] = "succeeded"
            task["result"] = dict(result or {})
            task["error"] = None
            task["finished_at"] = now
            task["updated_at"] = now
            return dict(task)

    def fail(self, task_id: str, error: str) -> Dict[str, Any]:
        with self._lock:
            task = self._tasks[task_id]
            now = self._now()
            task["error"] = str(error)
            task["finished_at"] = now
            task["updated_at"] = now
            if task["attempts"] >= task["max_attempts"]:
                task["status"] = "dead"
            else:
                task["status"] = "queued"
            return dict(task)

    def retry(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._tasks[task_id]
            if task["status"] not in {"failed", "dead"}:
                return dict(task)
            now = self._now()
            task["status"] = "queued"
            task["error"] = None
            task["finished_at"] = None
            task["updated_at"] = now
            return dict(task)


task_queue_service = TaskQueueService()
