# P2 Vector Store Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend-neutral vector search boundary while keeping Chroma as the default implementation.

**Architecture:** Define a small protocol and dataclasses for vector search, implement a Chroma adapter, then route `RAGTool._vector_search()` through the adapter. This phase only abstracts search, leaving ingestion and collection lifecycle on the existing Chroma code.

**Tech Stack:** Python 3, pytest, LangChain `Document`, existing Chroma collection objects, `test3` conda environment.

---

## File Structure

- Create `tools/rag/vector_store_backend.py`: backend-neutral request/result/capability dataclasses and protocol.
- Create `tools/rag/chroma_backend.py`: Chroma adapter implementing the search protocol.
- Modify `tools/rag_tool.py`: initialize and refresh `self.vector_backend`, delegate `_vector_search()` through it.
- Create `tests/admin/test_p2_vector_store_backend.py`: unit tests with fake collection and fake embedding objects.
- Create `docs/reports/2026-04-21-p2-vector-store-abstraction-report.md`: verification and residual risk report.

### Task 1: Vector Backend Contract Tests

**Files:**
- Create: `tests/admin/test_p2_vector_store_backend.py`

- [ ] **Step 1: Write the failing tests**

```python
from tools.rag.vector_store_backend import (
    VectorSearchRequest,
    VectorStoreCapabilities,
)
from tools.rag.chroma_backend import ChromaVectorStoreBackend


class FakeEmbeddings:
    def __init__(self):
        self.queries = []

    def embed_query(self, query):
        self.queries.append(query)
        return [0.1, 0.2, 0.3]


class FakeCollection:
    def __init__(self, results=None):
        self.results = results or {
            "documents": [["doc text"]],
            "metadatas": [[{"source": "unit"}]],
            "distances": [[0.12]],
            "ids": [["doc-1"]],
        }
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.results


def test_vector_store_contract_exposes_production_capabilities():
    request = VectorSearchRequest(
        query="refund policy",
        top_k=3,
        query_embedding=[0.4, 0.5],
        metadata_filter={"tenant_id": "tenant-a"},
    )
    capabilities = VectorStoreCapabilities(
        backend_name="chroma",
        supports_metadata_filter=True,
        supports_upsert=True,
        supports_delete=True,
    )

    assert request.query == "refund policy"
    assert request.top_k == 3
    assert request.metadata_filter == {"tenant_id": "tenant-a"}
    assert capabilities.backend_name == "chroma"
    assert capabilities.supports_metadata_filter is True
    assert capabilities.supports_tenant_isolation is False


def test_chroma_backend_search_passes_embedding_and_filter_to_collection():
    collection = FakeCollection()
    embeddings = FakeEmbeddings()
    backend = ChromaVectorStoreBackend(collection=collection, embeddings=embeddings)

    results = backend.search(
        VectorSearchRequest(
            query="hello",
            top_k=2,
            metadata_filter={"tenant_id": "tenant-a"},
        )
    )

    assert embeddings.queries == ["hello"]
    assert collection.calls == [
        {
            "query_embeddings": [[0.1, 0.2, 0.3]],
            "n_results": 2,
            "include": ["documents", "metadatas", "distances"],
            "where": {"tenant_id": "tenant-a"},
        }
    ]
    assert len(results) == 1
    assert results[0].content == "doc text"
    assert results[0].metadata == {"source": "unit"}
    assert results[0].score == 0.12
    assert results[0].id == "doc-1"


def test_chroma_backend_search_returns_empty_when_unavailable():
    backend = ChromaVectorStoreBackend(collection=None, embeddings=FakeEmbeddings(), available=False)

    assert backend.search(VectorSearchRequest(query="hello", top_k=2)) == []
```

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\agentlearn\miniconda\envs\test3\python.exe -m pytest tests/admin/test_p2_vector_store_backend.py -q
```

Expected: fail because `tools.rag.vector_store_backend` and `tools.rag.chroma_backend` do not exist.

### Task 2: Backend Contract and Chroma Adapter

**Files:**
- Create: `tools/rag/vector_store_backend.py`
- Create: `tools/rag/chroma_backend.py`

- [ ] **Step 1: Implement `tools/rag/vector_store_backend.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class VectorSearchRequest:
    query: str
    top_k: int = 3
    query_embedding: Optional[List[float]] = None
    metadata_filter: Optional[Dict[str, Any]] = None
    include: List[str] = field(default_factory=lambda: ["documents", "metadatas", "distances"])


@dataclass
class VectorSearchResult:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    id: Optional[str] = None


@dataclass(frozen=True)
class VectorStoreCapabilities:
    backend_name: str
    supports_metadata_filter: bool = False
    supports_tenant_isolation: bool = False
    supports_hybrid_search: bool = False
    supports_upsert: bool = False
    supports_delete: bool = False
    notes: str = ""


class VectorStoreBackend(Protocol):
    def search(self, request: VectorSearchRequest) -> List[VectorSearchResult]:
        ...

    def get_capabilities(self) -> VectorStoreCapabilities:
        ...
```

- [ ] **Step 2: Implement `tools/rag/chroma_backend.py`**

```python
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.rag.vector_store_backend import (
    VectorSearchRequest,
    VectorSearchResult,
    VectorStoreCapabilities,
)


class ChromaVectorStoreBackend:
    def __init__(self, collection: Any, embeddings: Any, backend_name: str = "chroma", available: bool = True):
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
                query_kwargs["where"] = request.metadata_filter

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
```

- [ ] **Step 3: Run adapter tests**

Run:

```powershell
D:\agentlearn\miniconda\envs\test3\python.exe -m pytest tests/admin/test_p2_vector_store_backend.py -q
```

Expected: `3 passed`.

### Task 3: RAGTool Search Delegation

**Files:**
- Modify: `tools/rag_tool.py`

- [ ] **Step 1: Add imports and backend attribute**

Add:

```python
from tools.rag.chroma_backend import ChromaVectorStoreBackend
from tools.rag.vector_store_backend import VectorSearchRequest
```

In `RAGTool.__init__`, initialize:

```python
self.vector_backend = None
```

- [ ] **Step 2: Add backend refresh helper**

Add inside `RAGTool`:

```python
def _refresh_vector_backend(self) -> None:
    if self._db_available and self.collection is not None:
        self.vector_backend = ChromaVectorStoreBackend(
            collection=self.collection,
            embeddings=self.embeddings,
            available=True,
        )
    else:
        self.vector_backend = None
```

- [ ] **Step 3: Delegate `_vector_search()`**

Keep existing collection readiness checks, then replace direct `self.collection.query(...)` formatting with:

```python
self._refresh_vector_backend()
if self.vector_backend is None:
    return []

backend_results = self.vector_backend.search(VectorSearchRequest(query=query, top_k=top_k))
documents = []
for result in backend_results:
    metadata = dict(result.metadata or {})
    source_file = metadata.get("file_path", "")
    if source_file and not os.path.exists(source_file):
        continue
    metadata["score"] = result.score
    documents.append(Document(page_content=result.content, metadata=metadata))
return documents
```

- [ ] **Step 4: Run regression tests**

Run:

```powershell
D:\agentlearn\miniconda\envs\test3\python.exe -m pytest tests/admin/test_p2_vector_store_backend.py -q
D:\agentlearn\miniconda\envs\test3\python.exe -m pytest tests/admin/test_p1_agent_hardening.py tests/admin/test_p0_rag_security_trace.py -q
D:\agentlearn\miniconda\envs\test3\python.exe -m py_compile tools/rag/vector_store_backend.py tools/rag/chroma_backend.py tools/rag_tool.py
```

Expected: tests pass and compile exits with code 0.

### Task 4: Report and Commit

**Files:**
- Create: `docs/reports/2026-04-21-p2-vector-store-abstraction-report.md`

- [ ] **Step 1: Write the report**

Include:

```markdown
# P2 Vector Store Abstraction Report

## Scope

- Added a backend-neutral vector search contract.
- Added a Chroma adapter for current retrieval.
- Routed `RAGTool._vector_search()` through the adapter.

## Verification

- `D:\agentlearn\miniconda\envs\test3\python.exe -m pytest tests/admin/test_p2_vector_store_backend.py -q`
- `D:\agentlearn\miniconda\envs\test3\python.exe -m pytest tests/admin/test_p1_agent_hardening.py tests/admin/test_p0_rag_security_trace.py -q`
- `D:\agentlearn\miniconda\envs\test3\python.exe -m py_compile tools/rag/vector_store_backend.py tools/rag/chroma_backend.py tools/rag_tool.py`

## Residual Risks

- Ingestion, deletion, rebuild, and stats paths still call Chroma directly.
- This phase does not add a second vector backend.
- Query quality and benchmark comparisons remain separate P2 work.
```

- [ ] **Step 2: Commit**

Run:

```powershell
git add docs/superpowers/specs/2026-04-21-p2-vector-store-abstraction-design.md docs/superpowers/plans/2026-04-21-p2-vector-store-abstraction.md docs/reports/2026-04-21-p2-vector-store-abstraction-report.md tests/admin/test_p2_vector_store_backend.py tools/rag/vector_store_backend.py tools/rag/chroma_backend.py tools/rag_tool.py
git commit -m "feat: add vector store abstraction"
```
