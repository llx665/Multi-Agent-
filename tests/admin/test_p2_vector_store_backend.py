from tools.rag.vector_store_backend import (
    VectorSearchRequest,
    VectorStoreCapabilities,
    build_vector_access_metadata,
    build_vector_metadata_filter,
    metadata_matches_filter,
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


def test_chroma_backend_search_wraps_multi_field_filter_with_and_operator():
    collection = FakeCollection()
    backend = ChromaVectorStoreBackend(collection=collection, embeddings=FakeEmbeddings())

    backend.search(
        VectorSearchRequest(
            query="hello",
            top_k=2,
            metadata_filter={
                "access_managed": True,
                "access_role_user": True,
            },
        )
    )

    assert collection.calls[0]["where"] == {
        "$and": [
            {"access_managed": True},
            {"access_role_user": True},
        ]
    }


def test_chroma_backend_search_returns_empty_when_unavailable():
    backend = ChromaVectorStoreBackend(
        collection=None,
        embeddings=FakeEmbeddings(),
        available=False,
    )

    assert backend.search(VectorSearchRequest(query="hello", top_k=2)) == []


def test_build_vector_metadata_filter_uses_non_default_tenant_and_safe_overrides():
    metadata_filter = build_vector_metadata_filter(
        {
            "tenant_id": "tenant-a",
            "user_role": "user",
            "vector_metadata_filter": {
                "department": "support",
                "visible_to_frontend": True,
                "allowed_roles": ["user"],
                "nested": {"unsafe": "shape"},
            },
        }
    )

    assert metadata_filter == {
        "tenant_id": "tenant-a",
        "access_managed": True,
        "access_published": True,
        "access_visible_to_frontend": True,
        "access_deleted": False,
        "access_role_user": True,
        "department": "support",
        "visible_to_frontend": True,
    }


def test_build_vector_metadata_filter_ignores_default_tenant():
    assert build_vector_metadata_filter({"tenant_id": "default"}) is None


def test_build_vector_metadata_filter_adds_operator_role_acl_filters():
    assert build_vector_metadata_filter({"user_role": "operator"}) == {
        "access_managed": True,
        "access_published": True,
        "access_visible_to_frontend": True,
        "access_deleted": False,
        "access_role_operator": True,
    }


def test_build_vector_metadata_filter_ignores_unknown_roles():
    assert build_vector_metadata_filter({"user_role": "guest"}) is None


def test_metadata_matches_filter_supports_hybrid_bm25_fallback_filtering():
    metadata_filter = {"tenant_id": "tenant-a", "visible_to_frontend": True}

    assert metadata_matches_filter(
        {"tenant_id": "tenant-a", "visible_to_frontend": True},
        metadata_filter,
    )
    assert not metadata_matches_filter(
        {"tenant_id": "tenant-b", "visible_to_frontend": True},
        metadata_filter,
    )


def test_build_vector_access_metadata_normalizes_registry_record_for_vector_filters():
    access_metadata = build_vector_access_metadata(
        source_metadata={"tenant_id": "tenant-a"},
        access_record={
            "document_id": "doc-alpha",
            "published": True,
            "visible_to_frontend": True,
            "allowed_roles": ["user", "admin"],
            "deleted": False,
        },
    )

    assert access_metadata == {
        "tenant_id": "tenant-a",
        "access_managed": True,
        "access_document_id": "doc-alpha",
        "access_published": True,
        "access_visible_to_frontend": True,
        "access_deleted": False,
        "access_role_user": True,
        "access_role_operator": False,
        "access_role_admin": True,
        "access_role_super_admin": False,
    }


def test_build_vector_access_metadata_denies_unmanaged_sources():
    access_metadata = build_vector_access_metadata(
        source_metadata={},
        access_record=None,
    )

    assert access_metadata["tenant_id"] == "default"
    assert access_metadata["access_managed"] is False
    assert access_metadata["access_published"] is False
    assert access_metadata["access_visible_to_frontend"] is False
    assert access_metadata["access_role_user"] is False
    assert access_metadata["access_role_operator"] is False
    assert access_metadata["access_role_admin"] is False
    assert access_metadata["access_role_super_admin"] is False


def test_vector_and_bm25_filters_exclude_role_inaccessible_documents():
    user_filter = build_vector_metadata_filter({"user_role": "user"})
    collection = FakeCollection(
        results={
            "documents": [["public doc"]],
            "metadatas": [[
                {
                    "access_managed": True,
                    "access_published": True,
                    "access_visible_to_frontend": True,
                    "access_deleted": False,
                    "access_role_user": True,
                }
            ]],
            "distances": [[0.1]],
            "ids": [["public-1"]],
        }
    )
    backend = ChromaVectorStoreBackend(collection=collection, embeddings=FakeEmbeddings())

    vector_results = backend.search(
        VectorSearchRequest(
            query="policy",
            top_k=5,
            metadata_filter=user_filter,
        )
    )
    bm25_candidates = [
        {
            "content": "public doc",
            "metadata": {
                "access_managed": True,
                "access_published": True,
                "access_visible_to_frontend": True,
                "access_deleted": False,
                "access_role_user": True,
            },
        },
        {
            "content": "operator doc",
            "metadata": {
                "access_managed": True,
                "access_published": True,
                "access_visible_to_frontend": True,
                "access_deleted": False,
                "access_role_user": False,
                "access_role_operator": True,
            },
        },
    ]

    bm25_results = [
        item for item in bm25_candidates if metadata_matches_filter(item["metadata"], user_filter)
    ]

    assert collection.calls[0]["where"] == {
        "$and": [{key: value} for key, value in user_filter.items()]
    }
    assert [result.content for result in vector_results] == ["public doc"]
    assert [item["content"] for item in bm25_results] == ["public doc"]
