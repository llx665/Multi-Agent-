"""Shared runtime dependencies for RAG across API and services."""

from __future__ import annotations

from typing import Dict


_rag_tool_instance = None


def get_rag_tool():
    """Return singleton RAG tool instance."""
    global _rag_tool_instance
    if _rag_tool_instance is None:
        from tools.rag_tool import rag_tool

        _rag_tool_instance = rag_tool
    return _rag_tool_instance


def get_loaded_rag_tool():
    """Return the loaded RAG tool instance without triggering initialization."""
    return _rag_tool_instance


class RAGParamsManager:
    """In-memory runtime parameter manager for RAG."""

    _instance = None
    _params = {
        "chunk_size": 400,
        "chunk_overlap": 50,
        "top_k": 5,
        "similarity_threshold": 0.3,
        "enable_cache": True,
        "enable_rerank": True,
        "enable_hybrid": True,
        "enable_self_rag": False,
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_params(self) -> Dict:
        return self._params.copy()

    def update_params(self, params: Dict):
        self._params.update(params)

    def get_chunk_size(self) -> int:
        return self._params["chunk_size"]

    def get_chunk_overlap(self) -> int:
        return self._params["chunk_overlap"]

    def get_top_k(self) -> int:
        return self._params["top_k"]

    def get_similarity_threshold(self) -> float:
        return self._params["similarity_threshold"]

    def get_enable_cache(self) -> bool:
        return self._params["enable_cache"]

    def get_enable_rerank(self) -> bool:
        return self._params["enable_rerank"]

    def get_enable_self_rag(self) -> bool:
        return self._params["enable_self_rag"]


rag_params_manager = RAGParamsManager()
