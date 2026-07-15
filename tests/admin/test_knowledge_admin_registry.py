import json
import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app.services.knowledge_admin_service as knowledge_admin_service_module
from app.services.knowledge_admin_service import knowledge_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "knowledge-admin-registry-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class FakeRagCollection:
    def __init__(self, metadatas=None):
        self._metadatas = metadatas or []

    def get(self, include=None):
        del include
        return {"metadatas": list(self._metadatas)}


class FakeLoadedRagTool:
    def __init__(self, metadatas=None):
        self.collection = FakeRagCollection(metadatas)


class FakePersistentClient:
    def __init__(self, metadatas=None):
        self._collection = FakeRagCollection(metadatas)

    def get_collection(self, _name):
        return self._collection


class KnowledgeAdminRegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir = self.temp_dir / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.temp_dir / "knowledge-registry.json"
        knowledge_admin_service.reconfigure(
            docs_dir=str(self.docs_dir),
            metadata_path=str(self.metadata_path),
        )

    def tearDown(self):
        knowledge_admin_service.reconfigure()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_registry_is_upgraded_and_preserves_access_flags(self):
        (self.docs_dir / "alpha.txt").write_text("alpha", encoding="utf-8")
        self.metadata_path.write_text(
            json.dumps(
                {
                    "alpha.txt": {
                        "visible_to_frontend": False,
                        "published": True,
                        "allowed_roles": ["admin"],
                        "updated_at": "2026-04-15T10:00:00",
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        documents = knowledge_admin_service.list_documents()

        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertTrue(document["document_id"].startswith("doc_"))
        self.assertEqual(document["filename"], "alpha.txt")
        self.assertEqual(document["allowed_roles"], ["admin"])
        self.assertEqual(document["published"], True)
        self.assertEqual(document["visible_to_frontend"], False)
        self.assertEqual(document["deleted"], False)
        self.assertEqual(document["chunk_count"], 0)

        saved = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["version"], 2)
        self.assertIn(document["document_id"], saved["documents"])

    def test_untracked_file_gets_default_registry_record(self):
        (self.docs_dir / "beta.txt").write_text("beta", encoding="utf-8")

        documents = knowledge_admin_service.list_documents()

        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertEqual(document["filename"], "beta.txt")
        self.assertEqual(document["published"], True)
        self.assertEqual(document["visible_to_frontend"], True)
        self.assertEqual(
            document["allowed_roles"],
            ["user", "operator", "admin", "super_admin"],
        )

    def test_existing_registry_record_reconciles_chunk_count_from_loaded_vector_store(self):
        alpha_path = self.docs_dir / "alpha.txt"
        alpha_path.write_text("line-1\nline-2\nline-3", encoding="utf-8")
        self.metadata_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "documents": {
                        "doc_alpha": {
                            "document_id": "doc_alpha",
                            "current_version_id": None,
                            "filename": "alpha.txt",
                            "file_type": ".txt",
                            "storage_name": "alpha.txt",
                            "storage_path": str(alpha_path.resolve()),
                            "size": alpha_path.stat().st_size,
                            "checksum": "legacy-checksum",
                            "chunk_count": 0,
                            "description": "",
                            "tags": [],
                            "published": True,
                            "visible_to_frontend": True,
                            "allowed_roles": ["user", "operator", "admin", "super_admin"],
                            "deleted": False,
                            "created_at": "2026-04-15T10:00:00",
                            "created_by": "admin-1",
                            "updated_at": "2026-04-15T10:00:00",
                            "updated_by": "admin-1",
                            "deleted_at": None,
                            "deleted_by": None,
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        rag_tool = FakeLoadedRagTool(
            [
                {"source_file": str(alpha_path.resolve())},
                {"source_file": str(alpha_path.resolve())},
                {"source_file": str(alpha_path.resolve())},
            ]
        )

        with patch("app.services.knowledge_admin_service.get_loaded_rag_tool", return_value=rag_tool, create=True):
            documents = knowledge_admin_service.list_documents()

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["chunk_count"], 3)

        saved = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["documents"]["doc_alpha"]["chunk_count"], 3)

    def test_existing_registry_record_reconciles_chunk_count_from_persistent_vector_store(self):
        alpha_path = self.docs_dir / "alpha.txt"
        alpha_path.write_text("line-1\nline-2\nline-3", encoding="utf-8")
        self.metadata_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "documents": {
                        "doc_alpha": {
                            "document_id": "doc_alpha",
                            "current_version_id": None,
                            "filename": "alpha.txt",
                            "file_type": ".txt",
                            "storage_name": "alpha.txt",
                            "storage_path": str(alpha_path.resolve()),
                            "size": alpha_path.stat().st_size,
                            "checksum": "legacy-checksum",
                            "chunk_count": 0,
                            "description": "",
                            "tags": [],
                            "published": True,
                            "visible_to_frontend": True,
                            "allowed_roles": ["user", "operator", "admin", "super_admin"],
                            "deleted": False,
                            "created_at": "2026-04-15T10:00:00",
                            "created_by": "admin-1",
                            "updated_at": "2026-04-15T10:00:00",
                            "updated_by": "admin-1",
                            "deleted_at": None,
                            "deleted_by": None,
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        client = FakePersistentClient(
            [
                {"source_file": str(alpha_path.resolve())},
                {"source_file": str(alpha_path.resolve())},
                {"source_file": str(alpha_path.resolve())},
            ]
        )

        with patch("app.services.knowledge_admin_service.get_loaded_rag_tool", return_value=None, create=True):
            with patch(
                "app.services.knowledge_admin_service.get_rag_tool",
                side_effect=AssertionError("should not initialize rag tool"),
                create=True,
            ):
                with patch(
                    "app.services.knowledge_admin_service._get_chromadb_module",
                    return_value=SimpleNamespace(PersistentClient=lambda path, settings=None: client),
                ):
                    documents = knowledge_admin_service.list_documents()

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["chunk_count"], 3)

    def test_persistent_vector_store_fallback_uses_rag_chroma_settings(self):
        alpha_path = self.docs_dir / "alpha.txt"
        alpha_path.write_text("alpha content", encoding="utf-8")
        self.metadata_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "documents": {
                        "doc_alpha": {
                            "document_id": "doc_alpha",
                            "current_version_id": None,
                            "filename": "alpha.txt",
                            "file_type": ".txt",
                            "storage_name": "alpha.txt",
                            "storage_path": str(alpha_path.resolve()),
                            "size": alpha_path.stat().st_size,
                            "checksum": "checksum-alpha",
                            "chunk_count": 0,
                            "description": "",
                            "tags": [],
                            "published": True,
                            "visible_to_frontend": True,
                            "allowed_roles": ["user", "operator", "admin", "super_admin"],
                            "deleted": False,
                            "created_at": "2026-04-15T10:00:00",
                            "created_by": "admin-1",
                            "updated_at": "2026-04-15T10:00:00",
                            "updated_by": "admin-1",
                            "deleted_at": None,
                            "deleted_by": None,
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        captured = {}
        client = FakePersistentClient([{"source_file": str(alpha_path.resolve())}])

        def persistent_client(path, settings=None):
            captured["path"] = path
            captured["settings"] = settings
            return client

        with patch("app.services.knowledge_admin_service.get_loaded_rag_tool", return_value=None, create=True):
            with patch(
                "app.services.knowledge_admin_service._get_chromadb_module",
                return_value=SimpleNamespace(PersistentClient=persistent_client),
            ):
                documents = knowledge_admin_service.list_documents()

        self.assertEqual(len(documents), 1)
        self.assertIsNotNone(captured.get("settings"))
        self.assertEqual(captured["settings"].anonymized_telemetry, False)

    def test_vector_access_metadata_for_source_uses_registry_record(self):
        alpha_path = self.docs_dir / "alpha.txt"
        alpha_path.write_text("alpha content", encoding="utf-8")
        self.metadata_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "documents": {
                        "doc_alpha": {
                            "document_id": "doc_alpha",
                            "current_version_id": None,
                            "filename": "alpha.txt",
                            "file_type": ".txt",
                            "storage_name": "alpha.txt",
                            "storage_path": str(alpha_path.resolve()),
                            "size": alpha_path.stat().st_size,
                            "checksum": "checksum-alpha",
                            "chunk_count": 0,
                            "description": "",
                            "tags": [],
                            "published": True,
                            "visible_to_frontend": True,
                            "allowed_roles": ["user", "admin"],
                            "deleted": False,
                            "created_at": "2026-04-22T00:00:00",
                            "created_by": "admin-1",
                            "updated_at": "2026-04-22T00:00:00",
                            "updated_by": "admin-1",
                            "deleted_at": None,
                            "deleted_by": None,
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        access_metadata = knowledge_admin_service.get_vector_access_metadata_for_source(
            str(alpha_path.resolve()),
            tenant_id="tenant-a",
        )

        self.assertEqual(access_metadata["tenant_id"], "tenant-a")
        self.assertEqual(access_metadata["access_managed"], True)
        self.assertEqual(access_metadata["access_document_id"], "doc_alpha")
        self.assertEqual(access_metadata["access_published"], True)
        self.assertEqual(access_metadata["access_visible_to_frontend"], True)
        self.assertEqual(access_metadata["access_role_user"], True)
        self.assertEqual(access_metadata["access_role_operator"], False)
        self.assertEqual(access_metadata["access_role_admin"], True)
        self.assertEqual(access_metadata["access_role_super_admin"], False)


if __name__ == "__main__":
    unittest.main()
