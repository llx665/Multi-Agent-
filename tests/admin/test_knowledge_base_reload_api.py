import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, knowledge_base
from app.services.auth_service import auth_service
from app.services.knowledge_admin_service import knowledge_admin_service
from app.services.task_queue_service import task_queue_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "knowledge-base-reload-api-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
user_app = FastAPI()
user_app.include_router(auth.router, prefix="/api/v1")
user_app.include_router(knowledge_base.router, prefix="/api/v1")


class FakeReloadRagTool:
    def __init__(self):
        self._db_available = True
        self.collection = self
        self.sources = {}
        self.loaded_sources = []

    def clear_and_rebuild_collection(self):
        self.sources = {}
        self.loaded_sources = []
        return True

    def load_document(self, source, chunk_size=400, chunk_overlap=50):
        del chunk_size, chunk_overlap
        self.loaded_sources.append(Path(source).name)
        suffix = Path(source).suffix.lower()
        if suffix in {".html", ".htm"}:
            return [{"metadata": {"source_file": source}, "page_content": "html-1"}]
        if suffix == ".xlsx":
            return [
                {"metadata": {"source_file": source}, "page_content": "xlsx-1"},
                {"metadata": {"source_file": source}, "page_content": "xlsx-2"},
            ]
        return [{"metadata": {"source_file": source}, "page_content": "txt-1"}]

    def add_documents_to_vector_db(self, documents):
        source = documents[0]["metadata"]["source_file"]
        self.sources[source] = len(documents)
        return [f"{source}:{index}" for index in range(len(documents))]

    def count(self):
        return sum(self.sources.values())


class KnowledgeBaseReloadApiTest(unittest.TestCase):
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

        self.client = TestClient(user_app)
        self.admin = auth_service.register("knowledge.reload.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        token = auth_service.create_token(self.admin["id"], self.admin["username"])["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

        self.rag_tool = FakeReloadRagTool()
        self.get_rag_tool_patcher = patch("app.api.v1.knowledge_base.get_rag_tool", return_value=self.rag_tool)
        self.get_rag_tool_patcher.start()

    def tearDown(self):
        self.get_rag_tool_patcher.stop()
        knowledge_admin_service.reconfigure()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_reload_queues_async_task(self):
        (self.docs_dir / "alpha.txt").write_text("alpha", encoding="utf-8")
        (self.docs_dir / "guide.html").write_text("<h1>Guide</h1><p>Step</p>", encoding="utf-8")
        (self.docs_dir / "table.xlsx").write_bytes(b"xlsx")
        (self.docs_dir / "ignore.json").write_text("{}", encoding="utf-8")

        response = self.client.post("/api/v1/knowledge-base/reload", headers=self.headers)

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload["task_id"].startswith("task_"))
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["message"], "knowledge reload queued")
        self.assertEqual(task_queue_service.get_task(payload["task_id"])["task_type"], "knowledge_reload")
        self.assertEqual(self.rag_tool.loaded_sources, [])


if __name__ == "__main__":
    unittest.main()
