import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.admin_main import app as admin_app
from app.services.auth_service import auth_service
from app.services.knowledge_admin_service import knowledge_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "knowledge-admin-phase2-api-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class FakeRagTool:
    def __init__(self):
        self._db_available = True
        self.collection = self
        self.source_chunks = {}

    def get(self, include=None):
        metadatas = []
        for source, count in self.source_chunks.items():
            metadatas.extend([{"source_file": source}] * count)
        return {"metadatas": metadatas}

    def count(self):
        return sum(self.source_chunks.values())

    def delete_documents_by_source(self, source):
        return self.source_chunks.pop(source, 0)

    def load_document(self, source, chunk_size=400, chunk_overlap=50):
        del chunk_size, chunk_overlap
        suffix = Path(source).suffix.lower()
        if suffix in {".html", ".htm"}:
            return [
                {"metadata": {"source_file": source}, "page_content": "html-chunk-0"},
                {"metadata": {"source_file": source}, "page_content": "html-chunk-1"},
            ]
        if suffix == ".xlsx":
            return [
                {"metadata": {"source_file": source}, "page_content": "xlsx-sheet-0"},
                {"metadata": {"source_file": source}, "page_content": "xlsx-sheet-1"},
            ]
        line_count = max(1, len(Path(source).read_text(encoding="utf-8").splitlines()))
        return [{"metadata": {"source_file": source}, "page_content": f"chunk-{index}"} for index in range(line_count)]

    def add_documents_to_vector_db(self, documents):
        source = documents[0]["metadata"]["source_file"]
        self.source_chunks[source] = len(documents)
        return [f"{source}::{index}" for index, _ in enumerate(documents)]


class KnowledgeAdminPhase2ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir = self.temp_dir / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.temp_dir / "knowledge-registry.json"
        self.audit_path = self.temp_dir / "admin-audit.jsonl"

        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        knowledge_admin_service.reconfigure(
            docs_dir=str(self.docs_dir),
            metadata_path=str(self.metadata_path),
            audit_storage_path=str(self.audit_path),
        )

        self.client = TestClient(admin_app)
        self.admin = auth_service.register("knowledge.phase2.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        token = auth_service.create_token(self.admin["id"], self.admin["username"])["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

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

    def test_admin_can_create_replace_delete_and_restore_document(self):
        create_response = self.client.post(
            "/api/admin/knowledge/documents",
            headers=self.headers,
            files={"file": ("alpha.txt", b"line-1\nline-2\nline-3", "text/plain")},
            data={
                "description": "alpha doc",
                "tags": '["faq","release"]',
                "allowed_roles": '["user","admin","super_admin"]',
                "published": "true",
                "visible_to_frontend": "false",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertTrue(created["document_id"].startswith("doc_"))
        self.assertEqual(created["chunk_count"], 3)
        self.assertEqual(created["tags"], ["faq", "release"])
        self.assertEqual(created["published"], True)

        replace_response = self.client.post(
            f"/api/admin/knowledge/documents/{created['document_id']}/replace",
            headers=self.headers,
            files={"file": ("alpha-v2.txt", b"line-1\nline-2", "text/plain")},
        )
        self.assertEqual(replace_response.status_code, 200)
        replaced = replace_response.json()
        self.assertEqual(replaced["document_id"], created["document_id"])
        self.assertEqual(replaced["filename"], "alpha-v2.txt")
        self.assertEqual(replaced["chunk_count"], 2)
        self.assertEqual(replaced["published"], True)

        delete_response = self.client.delete(
            f"/api/admin/knowledge/documents/{created['document_id']}",
            headers=self.headers,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["deleted"], True)

        restore_response = self.client.post(
            f"/api/admin/knowledge/documents/{created['document_id']}/restore",
            headers=self.headers,
        )
        self.assertEqual(restore_response.status_code, 200)
        restored = restore_response.json()
        self.assertEqual(restored["document_id"], created["document_id"])
        self.assertEqual(restored["published"], False)
        self.assertEqual(restored["visible_to_frontend"], False)

    def test_admin_can_upload_html_and_xlsx_documents(self):
        html_response = self.client.post(
            "/api/admin/knowledge/documents",
            headers=self.headers,
            files={"file": ("guide.html", b"<html><body><h1>Guide</h1></body></html>", "text/html")},
            data={
                "description": "html doc",
                "tags": '["guide"]',
                "allowed_roles": '["user","admin"]',
                "published": "false",
                "visible_to_frontend": "false",
            },
        )
        self.assertEqual(html_response.status_code, 200)
        self.assertEqual(html_response.json()["file_type"], ".html")

        xlsx_response = self.client.post(
            "/api/admin/knowledge/documents",
            headers=self.headers,
            files={
                "file": (
                    "table.xlsx",
                    b"PK\x03\x04\x14\x00\x00\x00\x08\x00fake-xlsx-content",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={
                "description": "xlsx doc",
                "tags": '["table"]',
                "allowed_roles": '["user","admin"]',
                "published": "false",
                "visible_to_frontend": "false",
            },
        )
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual(xlsx_response.json()["file_type"], ".xlsx")


if __name__ == "__main__":
    unittest.main()
