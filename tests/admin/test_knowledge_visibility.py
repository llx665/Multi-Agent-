import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin_main import app as admin_app
from app.api.v1 import auth, knowledge_base
from app.services.auth_service import auth_service
from app.services.knowledge_admin_service import knowledge_admin_service
from app.services.settings_admin_service import settings_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "knowledge-admin-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
user_app = FastAPI()
user_app.include_router(auth.router, prefix="/api/v1")
user_app.include_router(knowledge_base.router, prefix="/api/v1")


class FakeRagTool:
    def __init__(self):
        self._db_available = True
        self.collection = self
        self.source_chunks = {}

    def get(self, include=None):
        del include
        metadatas = []
        for source, count in self.source_chunks.items():
            metadatas.extend([{"source_file": source}] * count)
        return {"metadatas": metadatas}

    def count(self):
        return sum(self.source_chunks.values())

    def delete_documents_by_source(self, source):
        return self.source_chunks.pop(source, 0)


class KnowledgeVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir = self.temp_dir / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.temp_dir / "knowledge-registry.json"
        self.policy_path = self.temp_dir / "frontend_policy.json"
        self.audit_path = self.temp_dir / "admin_audit.jsonl"

        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        knowledge_admin_service.reconfigure(docs_dir=str(self.docs_dir), metadata_path=str(self.metadata_path))
        settings_admin_service.reconfigure(
            frontend_policy_path=str(self.policy_path),
            audit_storage_path=str(self.audit_path),
        )

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

        self.admin_client = TestClient(admin_app)
        self.user_client = TestClient(user_app)
        self.admin = auth_service.register("knowledge.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.operator = auth_service.register("knowledge.operator", "password123")
        auth_service.update_user_role(self.operator["id"], "operator")
        self.user = auth_service.register("knowledge.user", "password123")

        self.admin_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.admin['id'], self.admin['username'])['token']}"
        }
        self.operator_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.operator['id'], self.operator['username'])['token']}"
        }
        self.user_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.user['id'], self.user['username'])['token']}"
        }

        (self.docs_dir / "alpha.txt").write_text("alpha", encoding="utf-8")
        (self.docs_dir / "operator.txt").write_text("operator", encoding="utf-8")
        (self.docs_dir / "hidden.txt").write_text("hidden", encoding="utf-8")

        knowledge_admin_service.update_document_access(
            "alpha.txt",
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

    def tearDown(self):
        self.get_rag_tool_patcher.stop()
        self.get_loaded_rag_tool_patcher.stop()
        knowledge_admin_service.reconfigure()
        settings_admin_service.reconfigure()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_frontend_user_only_sees_role_allowed_published_documents(self):
        user_response = self.user_client.get("/api/v1/knowledge-base", headers=self.user_headers)
        operator_response = self.user_client.get("/api/v1/knowledge-base", headers=self.operator_headers)

        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(operator_response.status_code, 200)
        self.assertEqual([doc["filename"] for doc in user_response.json()["documents"]], ["alpha.txt"])
        self.assertEqual(
            [doc["filename"] for doc in operator_response.json()["documents"]],
            ["alpha.txt", "operator.txt"],
        )

    def test_frontend_list_uses_document_ids_and_metrics(self):
        admin_docs = self.admin_client.get(
            "/api/admin/knowledge/documents",
            headers=self.admin_headers,
        ).json()["documents"]
        alpha_doc = next(doc for doc in admin_docs if doc["filename"] == "alpha.txt")

        response = self.user_client.get("/api/v1/knowledge-base", headers=self.user_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["documents"]), 1)
        payload = response.json()["documents"][0]
        self.assertEqual(payload["id"], alpha_doc["document_id"])
        self.assertEqual(payload["filename"], "alpha.txt")
        self.assertIn("chunk_count", payload)

    def test_deleted_document_is_hidden_from_frontend(self):
        admin_docs = self.admin_client.get(
            "/api/admin/knowledge/documents",
            headers=self.admin_headers,
        ).json()["documents"]
        alpha_doc = next(doc for doc in admin_docs if doc["filename"] == "alpha.txt")

        delete_response = self.admin_client.delete(
            f"/api/admin/knowledge/documents/{alpha_doc['document_id']}",
            headers=self.admin_headers,
        )
        self.assertEqual(delete_response.status_code, 200)

        user_response = self.user_client.get("/api/v1/knowledge-base", headers=self.user_headers)
        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(user_response.json()["documents"], [])

    def test_admin_can_hide_document_from_frontend(self):
        response = self.admin_client.patch(
            "/api/admin/knowledge/documents/alpha.txt",
            json={"visible_to_frontend": False},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["visible_to_frontend"], False)

        user_response = self.user_client.get("/api/v1/knowledge-base", headers=self.user_headers)
        self.assertEqual([doc["filename"] for doc in user_response.json()["documents"]], [])

    def test_operator_cannot_update_document_visibility(self):
        response = self.admin_client.patch(
            "/api/admin/knowledge/documents/alpha.txt",
            json={"published": False},
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_frontend_params_response_includes_frontend_policy(self):
        response = self.user_client.get("/api/v1/knowledge-base/params", headers=self.user_headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("frontend_policy", payload)
        self.assertIn("knowledge_base", payload["frontend_policy"])
        self.assertIn("settings", payload["frontend_policy"])


if __name__ == "__main__":
    unittest.main()
