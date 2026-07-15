"""Cache key helpers for retrieval policy isolation."""

import hashlib
import json
from typing import Any, Dict, Optional


_POLICY_KEY_DEFAULTS = {
    "user_role": "anonymous",
    "tenant_id": "default",
    "knowledge_version": "unknown",
    "enable_hybrid": None,
    "enable_rerank": None,
}


def normalize_retrieval_policy(retrieval_policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    policy = {**_POLICY_KEY_DEFAULTS}
    if retrieval_policy:
        for key in _POLICY_KEY_DEFAULTS:
            value = retrieval_policy.get(key)
            if value is not None:
                policy[key] = value
    return policy


def build_retrieval_cache_key(
    query: str,
    top_k: int,
    enable_self_rag: bool,
    *,
    retrieval_policy: Optional[Dict[str, Any]] = None,
) -> str:
    payload = {
        "query": query,
        "top_k": top_k,
        "enable_self_rag": enable_self_rag,
        "retrieval_policy": normalize_retrieval_policy(retrieval_policy),
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(content.encode("utf-8")).hexdigest()
