from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.services.audit_log_service import AuditLogService
from app.services.frontend_policy_store import FrontendPolicyStore
from app.services.rag_runtime import get_loaded_rag_tool, rag_params_manager


class SettingsAdminValidationError(ValueError):
    pass


class SettingsAdminService:
    def __init__(self) -> None:
        self.reconfigure()

    def reconfigure(
        self,
        frontend_policy_path: Optional[str] = None,
        audit_storage_path: Optional[str] = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[3]
        self.frontend_policy_store = FrontendPolicyStore(
            frontend_policy_path or str(project_root / "data" / "settings" / "frontend_policy.json")
        )
        self.audit_log_service = AuditLogService(
            storage_path=audit_storage_path or str(project_root / "logs" / "admin_audit.jsonl")
        )

    @staticmethod
    def _permission_model() -> Dict[str, Dict[str, object]]:
        return {
            "roles": {
                "super_admin": {
                    "label": "超级管理员",
                    "capabilities": ["全部后台模块", "角色与权限策略", "系统安全配置", "知识库发布控制"],
                },
                "admin": {
                    "label": "管理员",
                    "capabilities": ["记忆管理", "知识库显隐与发布", "系统设置", "账号管理"],
                },
                "operator": {
                    "label": "运营",
                    "capabilities": ["查看后台总览", "记忆管理", "查看知识库模块"],
                },
                "user": {
                    "label": "前台用户",
                    "capabilities": ["对话", "只读知识库", "只读设置摘要"],
                },
            }
        }

    @staticmethod
    def _validate_runtime_params(params: Dict[str, object]) -> None:
        if int(params["chunk_size"]) < 100:
            raise SettingsAdminValidationError("chunk_size must be >= 100")
        if int(params["chunk_overlap"]) < 0:
            raise SettingsAdminValidationError("chunk_overlap must be >= 0")
        if int(params["chunk_overlap"]) >= int(params["chunk_size"]):
            raise SettingsAdminValidationError("chunk_overlap must be smaller than chunk_size")
        if int(params["top_k"]) < 1:
            raise SettingsAdminValidationError("top_k must be >= 1")
        if not 0 <= float(params["similarity_threshold"]) <= 1:
            raise SettingsAdminValidationError("similarity_threshold must be between 0 and 1")

    def _validate_frontend_policy(self, payload: Dict[str, object]) -> Dict[str, object]:
        if not isinstance(payload, dict):
            raise SettingsAdminValidationError("frontend policy payload must be an object")

        allowed = {
            "knowledge_base": {
                "intro_text": str,
                "empty_state_text": str,
                "readonly_notice": str,
                "show_document_metrics": bool,
            },
            "settings": {
                "show_summary": bool,
                "show_runtime_overview": bool,
                "show_permission_notice": bool,
                "readonly_notice": str,
            },
        }

        extra_groups = set(payload.keys()) - set(allowed.keys())
        if extra_groups:
            raise SettingsAdminValidationError(f"unsupported frontend policy groups: {sorted(extra_groups)}")

        normalized: Dict[str, Any] = {}
        for group, schema in allowed.items():
            section = payload.get(group) or {}
            if not isinstance(section, dict):
                raise SettingsAdminValidationError(f"{group} must be an object")
            extra_fields = set(section.keys()) - set(schema.keys())
            if extra_fields:
                raise SettingsAdminValidationError(f"unsupported frontend policy fields: {sorted(extra_fields)}")
            for field_name, field_type in schema.items():
                if field_name in section and not isinstance(section[field_name], field_type):
                    raise SettingsAdminValidationError(f"{group}.{field_name} must be of type {field_type.__name__}")
            normalized[group] = section

        return self.frontend_policy_store.merge_with_defaults(normalized)

    def get_frontend_policy(self) -> Dict[str, object]:
        return self.frontend_policy_store.load()

    def get_summary(self) -> Dict[str, object]:
        return {
            "runtime_params": rag_params_manager.get_params(),
            "permission_model": self._permission_model(),
            "frontend_policy": self.get_frontend_policy(),
        }

    def update_frontend_policy(self, payload: Dict[str, object], actor_id: Optional[str] = None) -> Dict[str, object]:
        policy = self._validate_frontend_policy(payload)
        saved = self.frontend_policy_store.save(policy)

        if actor_id:
            self.audit_log_service.write(
                actor_id=actor_id,
                module="settings",
                action="update_frontend_policy",
                target_type="frontend_policy",
                target_id="global",
                result="success",
                extra={"groups": sorted(saved.keys())},
            )

        return saved

    def update_runtime_params(self, params: Dict[str, object], actor_id: Optional[str] = None) -> Dict[str, object]:
        self._validate_runtime_params(params)
        rag_params_manager.update_params(params)

        try:
            rag_tool = get_loaded_rag_tool()
            if rag_tool is None:
                raise RuntimeError("rag tool not loaded")

            from langchain_text_splitters import RecursiveCharacterTextSplitter
            from tools.rag_tool import LocalCache

            rag_tool.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=int(params["chunk_size"]),
                chunk_overlap=int(params["chunk_overlap"]),
                separators=["\n\n", "\n", ".", "?", "!", ",", "。", "，", "；", "："],
            )

            if params.get("enable_cache"):
                if hasattr(rag_tool, "_create_redis_cache"):
                    try:
                        rag_tool.cache = rag_tool._create_redis_cache()
                    except Exception:
                        rag_tool.cache = LocalCache(max_size=1000, default_ttl=3600)
                else:
                    rag_tool.cache = LocalCache(max_size=1000, default_ttl=3600)
            else:
                rag_tool.cache = LocalCache(max_size=1000, default_ttl=3600)

            if not params.get("enable_rerank") and hasattr(rag_tool, "reranker"):
                rag_tool.reranker = None
            elif params.get("enable_rerank") and getattr(rag_tool, "reranker", None) is None:
                from tools.rag_tool import Reranker

                rag_tool.reranker = Reranker()
        except Exception as exc:
            print(f"[WARN] failed to apply runtime params into rag tool: {exc}")

        if actor_id:
            self.audit_log_service.write(
                actor_id=actor_id,
                module="settings",
                action="update_runtime",
                target_type="rag_params",
                target_id="runtime",
                result="success",
                extra={"chunk_size": params.get("chunk_size"), "top_k": params.get("top_k")},
            )

        return rag_params_manager.get_params()


settings_admin_service = SettingsAdminService()
