from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


DEFAULT_FRONTEND_POLICY = {
    "knowledge_base": {
        "intro_text": "这里仅展示当前账号角色允许访问且已发布的知识文件。",
        "empty_state_text": "当前角色暂无可访问的知识文件。",
        "readonly_notice": "知识文件的编辑、发布和访问规则统一在后台维护。",
        "show_document_metrics": True,
    },
    "settings": {
        "show_summary": True,
        "show_runtime_overview": True,
        "show_permission_notice": True,
        "readonly_notice": "前台仅保留系统摘要，正式配置请在后台维护。",
    },
}


class FrontendPolicyStore:
    def __init__(self, storage_path: str) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.storage_path.exists():
            return deepcopy(DEFAULT_FRONTEND_POLICY)
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return deepcopy(DEFAULT_FRONTEND_POLICY)
        return self.merge_with_defaults(raw)

    def save(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        merged = self.merge_with_defaults(policy)
        self.storage_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def merge_with_defaults(self, policy: Dict[str, Any] | None) -> Dict[str, Any]:
        merged = deepcopy(DEFAULT_FRONTEND_POLICY)
        if not isinstance(policy, dict):
            return merged
        for group in ("knowledge_base", "settings"):
            section = policy.get(group)
            if isinstance(section, dict):
                merged[group].update(section)
        return merged
