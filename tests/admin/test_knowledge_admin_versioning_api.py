import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.admin_main import app as admin_app
from app.services.auth_service import auth_service
from app.services.knowledge_admin_service import knowledge_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "knowledge-admin-versioning-api-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class FakeRagTool:
    def __init__(self):
        self.source_chunks = {}

    def load_document(self, source, chunk_size=400, chunk_overlap=50):
        del chunk_size, chunk_overlap
        line_count = max(1, len(Path(source).read_text(encoding="utf-8").splitlines()))
        return [{"metadata": {"source_file": source}, "page_content": f"chunk-{index}"} for index in range(line_count)]

    def add_documents_to_vector_db(self, documents):
        source = documents[0]["metadata"]["source_file"]
        self.source_chunks[source] = len(documents)
        return [f"{source}::{index}" for index, _ in enumerate(documents)]

    def delete_documents_by_source(self, source):
        return self.source_chunks.pop(source, 0)


class KnowledgeAdminVersioningApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir = self.temp_dir / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir = self.temp_dir / "history"
        self.metadata_path = self.temp_dir / "knowledge-registry.json"
        self.audit_path = self.temp_dir / "admin-audit.jsonl"
        db_path = self.temp_dir / "auth.sqlite3"

        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        knowledge_admin_service.reconfigure(
            docs_dir=str(self.docs_dir),
            metadata_path=str(self.metadata_path),
            audit_storage_path=str(self.audit_path),
            history_dir=str(self.history_dir),
        )

        self.client = TestClient(admin_app)
        self.admin = auth_service.register("knowledge.phase3.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.operator = auth_service.register("knowledge.phase3.operator", "password123")
        auth_service.update_user_role(self.operator["id"], "operator")
        self.admin_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.admin['id'], self.admin['username'])['token']}"
        }
        self.operator_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.operator['id'], self.operator['username'])['token']}"
        }

        self.rag_tool = FakeRagTool()
        self.get_rag_tool_patcher = patch(
            "app.services.knowledge_admin_service.get_rag_tool",
            return_value=self.rag_tool,
            create=True,
        )
        self.get_loaded_rag_tool_patcher = patch(
            "app.services.knowledge_admin_service.get_loaded_rag_tool",
            return_value=self.rag_tool,
            create=True,
        )
        self.get_rag_tool_patcher.start()
        self.get_loaded_rag_tool_patcher.start()

    def tearDown(self):
        self.get_rag_tool_patcher.stop()
        self.get_loaded_rag_tool_patcher.stop()
        knowledge_admin_service.reconfigure()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_operator_can_list_versions_and_admin_can_rollback(self):
        created = knowledge_admin_service.create_document(
            filename="alpha.txt",
            content=b"line-1\nline-2\nline-3",
            actor_id=self.admin["id"],
            description="alpha v1",
            tags=["faq"],
            published=True,
            visible_to_frontend=False,
            allowed_roles=["user", "admin"],
        )
        knowledge_admin_service.replace_document(
            created["document_id"],
            filename="alpha-v2.txt",
            content=b"line-1\nline-2",
            actor_id=self.admin["id"],
        )

        versions_response = self.client.get(
            f"/api/admin/knowledge/documents/{created['document_id']}/versions",
            headers=self.operator_headers,
        )
        self.assertEqual(versions_response.status_code, 200)
        self.assertEqual(len(versions_response.json()["versions"]), 2)

        detail_response = self.client.get(
            f"/api/admin/knowledge/documents/{created['document_id']}/versions/{created['current_version_id']}",
            headers=self.operator_headers,
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["version_id"], created["current_version_id"])

        rollback_response = self.client.post(
            f"/api/admin/knowledge/documents/{created['document_id']}/rollback",
            json={"target_version_id": created["current_version_id"], "reason": "restore stable"},
            headers=self.admin_headers,
        )
        self.assertEqual(rollback_response.status_code, 200)
        self.assertEqual(rollback_response.json()["target_version_id"], created["current_version_id"])
        self.assertIn("new_version_id", rollback_response.json())


if __name__ == "__main__":
    unittest.main()
