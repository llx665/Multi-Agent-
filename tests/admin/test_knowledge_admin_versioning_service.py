import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app.services.knowledge_admin_service import KnowledgeConflictError, knowledge_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "knowledge-admin-versioning-service-tests"
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


class KnowledgeAdminVersioningServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir = self.temp_dir / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir = self.temp_dir / "history"
        self.metadata_path = self.temp_dir / "knowledge-registry.json"
        self.audit_path = self.temp_dir / "admin-audit.jsonl"
        knowledge_admin_service.reconfigure(
            docs_dir=str(self.docs_dir),
            metadata_path=str(self.metadata_path),
            audit_storage_path=str(self.audit_path),
            history_dir=str(self.history_dir),
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

    def tearDown(self):
        self.get_rag_tool_patcher.stop()
        self.get_loaded_rag_tool_patcher.stop()
        knowledge_admin_service.reconfigure()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_and_replace_append_immutable_versions(self):
        created = knowledge_admin_service.create_document(
            filename="alpha.txt",
            content=b"line-1\nline-2\nline-3",
            actor_id="admin-1",
            description="alpha doc",
            tags=["faq"],
            published=True,
            visible_to_frontend=True,
            allowed_roles=["user", "admin"],
        )

        replaced = knowledge_admin_service.replace_document(
            created["document_id"],
            filename="alpha-v2.txt",
            content=b"line-1\nline-2",
            actor_id="admin-2",
        )

        manifest_path = self.history_dir / created["document_id"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["document_id"], created["document_id"])
        self.assertEqual(manifest["latest_version_no"], 2)
        self.assertEqual(manifest["current_version_id"], replaced["current_version_id"])
        self.assertEqual([item["action"] for item in manifest["versions"]], ["create", "replace"])
        self.assertEqual(manifest["versions"][0]["filename"], "alpha.txt")
        self.assertEqual(manifest["versions"][1]["filename"], "alpha-v2.txt")
        self.assertTrue(Path(manifest["versions"][0]["snapshot_storage_path"]).exists())
        self.assertTrue(Path(manifest["versions"][1]["snapshot_storage_path"]).exists())

    def test_rollback_creates_new_current_version_without_changing_operating_flags(self):
        created = knowledge_admin_service.create_document(
            filename="alpha.txt",
            content=b"line-1\nline-2\nline-3",
            actor_id="admin-1",
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
            actor_id="admin-2",
        )
        knowledge_admin_service.update_document_metadata(
            created["document_id"],
            actor_id="admin-2",
            description="edited on v2",
            tags=["release"],
            visible_to_frontend=True,
            published=True,
            allowed_roles=["admin"],
        )

        rolled = knowledge_admin_service.rollback_document(
            created["document_id"],
            target_version_id=created["current_version_id"],
            actor_id="admin-3",
            reason="restore stable",
        )
        manifest = json.loads((self.history_dir / created["document_id"] / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(rolled["filename"], "alpha.txt")
        self.assertEqual(rolled["description"], "alpha v1")
        self.assertEqual(rolled["tags"], ["faq"])
        self.assertEqual(rolled["published"], True)
        self.assertEqual(rolled["visible_to_frontend"], True)
        self.assertEqual(rolled["allowed_roles"], ["admin"])
        self.assertEqual(manifest["latest_version_no"], 3)
        self.assertEqual(manifest["versions"][-1]["action"], "rollback")
        self.assertEqual(manifest["versions"][-1]["source_version_id"], created["current_version_id"])

    def test_deleted_document_cannot_be_rolled_back(self):
        created = knowledge_admin_service.create_document(
            filename="deleted.txt",
            content=b"line-1\nline-2",
            actor_id="admin-1",
        )
        knowledge_admin_service.delete_document(created["document_id"], actor_id="admin-2")

        with self.assertRaisesRegex(ValueError, "restore the document before rollback"):
            knowledge_admin_service.rollback_document(
                created["document_id"],
                target_version_id=created["current_version_id"],
                actor_id="admin-3",
            )

    def test_rollback_keeps_current_state_when_audit_write_fails(self):
        created = knowledge_admin_service.create_document(
            filename="alpha.txt",
            content=b"line-1\nline-2\nline-3",
            actor_id="admin-1",
            description="alpha v1",
            tags=["faq"],
        )
        replaced = knowledge_admin_service.replace_document(
            created["document_id"],
            filename="alpha-v2.txt",
            content=b"line-1\nline-2",
            actor_id="admin-2",
        )
        manifest_path = self.history_dir / created["document_id"] / "manifest.json"
        before_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        before_current = knowledge_admin_service.get_document(created["document_id"])
        before_bytes = (self.docs_dir / "alpha-v2.txt").read_bytes()

        with patch.object(knowledge_admin_service.audit_log_service, "write", side_effect=OSError("audit offline")):
            with self.assertRaisesRegex(OSError, "audit offline"):
                knowledge_admin_service.rollback_document(
                    created["document_id"],
                    target_version_id=created["current_version_id"],
                    actor_id="admin-3",
                    reason="restore stable",
                )

        after_current = knowledge_admin_service.get_document(created["document_id"])
        after_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(after_current["filename"], replaced["filename"])
        self.assertEqual(after_current["checksum"], before_current["checksum"])
        self.assertEqual(after_current["current_version_id"], before_current["current_version_id"])
        self.assertEqual((self.docs_dir / "alpha-v2.txt").read_bytes(), before_bytes)
        self.assertEqual(after_manifest, before_manifest)

    def test_corrupted_manifest_is_rejected_instead_of_resetting_history(self):
        created = knowledge_admin_service.create_document(
            filename="alpha.txt",
            content=b"line-1\nline-2\nline-3",
            actor_id="admin-1",
        )
        manifest_path = self.history_dir / created["document_id"] / "manifest.json"
        before_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_path.write_text("{broken json", encoding="utf-8")

        with self.assertRaisesRegex(KnowledgeConflictError, "manifest"):
            knowledge_admin_service.list_document_versions(created["document_id"])

        with self.assertRaisesRegex(KnowledgeConflictError, "manifest"):
            knowledge_admin_service.replace_document(
                created["document_id"],
                filename="alpha-v2.txt",
                content=b"line-1\nline-2",
                actor_id="admin-2",
            )

        self.assertEqual((self.docs_dir / "alpha.txt").read_text(encoding="utf-8"), "line-1\nline-2\nline-3")
        self.assertEqual(before_manifest["latest_version_no"], 1)


if __name__ == "__main__":
    unittest.main()
