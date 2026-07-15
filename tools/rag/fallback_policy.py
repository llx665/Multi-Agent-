"""Fallback decisions for low-quality RAG retrieval."""

from typing import Any, Dict, Optional


LOW_QUALITY_VALUES = {"none", "low", "missing", "empty"}


def _normalize_quality(quality: Optional[Any]) -> str:
    if quality is None:
        return ""
    if hasattr(quality, "value"):
        return str(quality.value).lower()
    return str(quality).lower()


def _rewrite_query(query: str) -> str:
    normalized = " ".join(str(query or "").split())
    if not normalized:
        return "补充产品型号、问题现象、业务场景后重新检索"
    return f"{normalized} 相关说明 处理步骤 常见原因"


def plan_low_quality_rag_fallback(
    query: str,
    retrieval_result: Optional[Dict[str, Any]] = None,
    quality: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return a deterministic fallback plan for empty or low-quality retrieval."""
    retrieval_result = retrieval_result or {}
    documents = retrieval_result.get("documents") or []
    quality_value = _normalize_quality(quality)
    has_relevant_info = bool(retrieval_result.get("has_relevant_info"))

    low_quality = not documents or quality_value in LOW_QUALITY_VALUES or not has_relevant_info
    if not low_quality:
        return {"needed": False, "strategy": "none"}

    return {
        "needed": True,
        "strategy": "clarify_and_rewrite",
        "rewrite_query": _rewrite_query(query),
        "clarification_message": "当前知识库命中不足，请补充产品型号、报错现象或使用场景后我再继续排查。",
        "retry_options": {
            "top_k": max(5, int(retrieval_result.get("top_k") or 3) + 2),
            "enable_hybrid": True,
            "enable_rerank": True,
        },
    }
