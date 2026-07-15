import shutil
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.knowledge_admin_service import knowledge_admin_service
from core.session_context import SessionContext


TEST_TMP_ROOT = PROJECT_ROOT / ".pytest_cache" / "p0-rag-security-trace-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def test_local_cache_isolates_entries_by_retrieval_policy():
    from tools.rag.cache_policy import build_retrieval_cache_key

    user_policy = {
        "user_role": "user",
        "tenant_id": "tenant-a",
        "knowledge_version": "v1",
        "enable_hybrid": True,
        "enable_rerank": False,
    }
    operator_policy = {**user_policy, "user_role": "operator"}

    user_key = build_retrieval_cache_key("X12 Pro", 3, True, retrieval_policy=user_policy)
    operator_key = build_retrieval_cache_key("X12 Pro", 3, True, retrieval_policy=operator_policy)

    assert user_key != operator_key
    assert user_key == build_retrieval_cache_key("X12 Pro", 3, True, retrieval_policy=user_policy)


def test_knowledge_admin_filters_retrieved_documents_by_frontend_access_policy():
    temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
    docs_dir = temp_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = temp_dir / "knowledge-registry.json"
    audit_path = temp_dir / "admin-audit.jsonl"

    try:
        knowledge_admin_service.reconfigure(
            docs_dir=str(docs_dir),
            metadata_path=str(metadata_path),
            audit_storage_path=str(audit_path),
        )

        public_doc = docs_dir / "public.txt"
        operator_doc = docs_dir / "operator.txt"
        hidden_doc = docs_dir / "hidden.txt"
        public_doc.write_text("public", encoding="utf-8")
        operator_doc.write_text("operator", encoding="utf-8")
        hidden_doc.write_text("hidden", encoding="utf-8")

        knowledge_admin_service.update_document_access(
            "public.txt",
            visible_to_frontend=True,
            published=True,
            allowed_roles=["user", "operator", "admin", "super_admin"],
        )
        knowledge_admin_service.update_document_access(
            "operator.txt",
            visible_to_frontend=True,
            published=True,
            allowed_roles=["operator", "admin", "super_admin"],
        )
        knowledge_admin_service.update_document_access(
            "hidden.txt",
            visible_to_frontend=False,
            published=True,
            allowed_roles=["user", "operator", "admin", "super_admin"],
        )

        retrieved = [
            {"content": "public", "source_file": str(public_doc.resolve())},
            {"content": "operator", "source_file": str(operator_doc.resolve())},
            {"content": "hidden", "source_file": str(hidden_doc.resolve())},
            {"content": "unknown", "source_file": str((docs_dir / "unknown.txt").resolve())},
        ]

        filtered = knowledge_admin_service.filter_retrieved_documents_for_role(retrieved, role="user")

        assert [doc["content"] for doc in filtered] == ["public"]
        assert filtered[0]["metadata"]["access_policy"]["published"] is True
    finally:
        knowledge_admin_service.reconfigure()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_session_context_records_trace_id_on_turns_and_summary():
    trace_id = "trace-test-001"
    context = SessionContext(session_id="trace-session", user_id="trace-user")

    context.add_turn(
        role="user",
        content="推荐耳机",
        agent_name="supervisor",
        intent="sales",
        trace_id=trace_id,
    )

    assert context.turn_history[-1].trace_id == trace_id
    assert context.get_session_summary()["trace_id"] == trace_id
