from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


class AuditLogService:
    def __init__(self, storage_path: Optional[str] = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.storage_path = storage_path or os.path.join(project_root, "logs", "admin_audit.jsonl")
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

    def write(
        self,
        actor_id: str,
        module: str,
        action: str,
        target_type: str,
        target_id: str,
        result: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "actor_id": actor_id,
            "module": module,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "result": result,
            "timestamp": int(time.time()),
        }
        if extra:
            payload["extra"] = extra
        with open(self.storage_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload


audit_log_service = AuditLogService()
