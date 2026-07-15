from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.rag.vector_store_backend import (
    VectorSearchRequest,
    VectorSearchResult,
    VectorStoreCapabilities,
)


class ChromaVectorStoreBackend:
    def __init__(
        self,
        collection: Any,
        embeddings: Any,
        backend_name: str = "chroma",
        available: bool = True,
    ):
        self.collection = collection
        self.embeddings = embeddings
        self.backend_name = backend_name
        self.available = available

    def get_capabilities(self) -> VectorStoreCapabilities:
        return VectorStoreCapabilities(
            backend_name=self.backend_name,
            supports_metadata_filter=True,
            supports_upsert=True,
            supports_delete=True,
            notes="Search adapter over the existing Chroma collection.",
        )

    def search(self, request: VectorSearchRequest) -> List[VectorSearchResult]:
        if not self.available or self.collection is None:
            return []

        try:
            query_embedding = request.query_embedding
            if query_embedding is None:
                query_embedding = self.embeddings.embed_query(request.query)

            query_kwargs: Dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": request.top_k,
                "include": request.include,
            }
            if request.metadata_filter:
                query_kwargs["where"] = self._build_where_filter(request.metadata_filter)

            raw_results = self.collection.query(**query_kwargs)
        except Exception:
            return []

        return self._format_results(raw_results)

    def _format_results(self, raw_results: Dict[str, Any]) -> List[VectorSearchResult]:
        documents = self._first_result_page(raw_results.get("documents"))
        metadatas = self._first_result_page(raw_results.get("metadatas"))
        distances = self._first_result_page(raw_results.get("distances"))
        ids = self._first_result_page(raw_results.get("ids"))

        results: List[VectorSearchResult] = []
        for index, content in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
            score = distances[index] if index < len(distances) and distances[index] is not None else 0.0
            result_id: Optional[str] = ids[index] if index < len(ids) else None
            results.append(
                VectorSearchResult(
                    content=content or "",
                    metadata=dict(metadata),
                    score=float(score),
                    id=result_id,
                )
            )
        return results

    @staticmethod
    def _first_result_page(value: Any) -> List[Any]:
        if not value:
            return []
        if isinstance(value, list) and value and isinstance(value[0], list):
            return value[0]
        if isinstance(value, list):
            return value
        return []

    @staticmethod
    def _build_where_filter(metadata_filter: Dict[str, Any]) -> Dict[str, Any]:
        if len(metadata_filter) <= 1:
            return dict(metadata_filter)
        return {"$and": [{key: value} for key, value in metadata_filter.items()]}
