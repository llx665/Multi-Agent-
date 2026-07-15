# P2 Vector Store Abstraction Design

## Goal

Introduce a small vector store boundary so the Agent/RAG stack stops depending on Chroma query details directly in the retrieval path.

## Scope

- Add a typed search contract for vector backends.
- Add a Chroma adapter that wraps the current collection and embedding behavior.
- Refactor `RAGTool._vector_search()` to call the adapter while preserving existing document formatting, deleted-file filtering, and fallback behavior.
- Keep Chroma as the default runtime backend.

## Non-goals

- No Milvus, Qdrant, Pinecone, or external vector service dependency in this phase.
- No rewrite of document ingestion, deletion, rebuild, or stats paths.
- No benchmark framework or distributed retrieval changes.
- No frontend changes.

## Architecture

`tools/rag/vector_store_backend.py` defines the stable contract:

- `VectorSearchRequest`: query text, optional precomputed embedding, top-k, optional metadata filter.
- `VectorSearchResult`: content, metadata, score, optional backend id.
- `VectorStoreCapabilities`: explicit feature flags that production code and future admin diagnostics can inspect.
- `VectorStoreBackend`: protocol with `search()` and `get_capabilities()`.

`tools/rag/chroma_backend.py` implements this contract for the existing Chroma collection. It owns the Chroma-specific call shape (`query_embeddings`, `where`, `include`) and converts Chroma results into backend-neutral result objects.

`tools/rag_tool.py` keeps its existing initialization and collection lifecycle. The only retrieval-path change is that `_vector_search()` refreshes a Chroma adapter for the active collection and asks it for search results.

## Data Flow

1. `RAGTool._vector_search(query, top_k)` ensures the collection is ready using current logic.
2. It refreshes `self.vector_backend` from `self.collection` and `self.embeddings`.
3. It calls `self.vector_backend.search(VectorSearchRequest(query=query, top_k=top_k))`.
4. It converts neutral results back to LangChain `Document` objects for existing RAG code.
5. It keeps existing stale file filtering before returning documents.

## Risk Controls

- The adapter catches backend query failures and returns an empty result set, matching current retrieval fallback behavior.
- Tests use fake collection and fake embeddings, so no Chroma service or persisted data is required.
- Existing P0/P1 tests run after the refactor to catch regressions in security filtering, cache policy, tracing, and graph behavior.

## Success Criteria

- Contract and Chroma adapter tests pass in `test3`.
- Existing P0/P1 tests still pass in `test3`.
- Changed Python files compile in `test3`.
- A P2 report records scope, verification commands, and residual risks.
