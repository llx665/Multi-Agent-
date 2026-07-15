import json
import shutil
import unittest
import uuid
from pathlib import Path

from app.services.rag_runtime import rag_params_manager
from app.services.settings_admin_service import SettingsAdminValidationError, settings_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "settings-admin-service-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class SettingsAdminServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.policy_path = self.temp_dir / "frontend_policy.json"
        self.audit_path = self.temp_dir / "admin_audit.jsonl"
        self.original_params = rag_params_manager.get_params()
        settings_admin_service.reconfigure(
            frontend_policy_path=str(self.policy_path),
            audit_storage_path=str(self.audit_path),
        )

    def tearDown(self):
        rag_params_manager.update_params(self.original_params)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_summary_uses_default_frontend_policy_when_file_missing(self):
        summary = settings_admin_service.get_summary()

        self.assertIn("frontend_policy", summary)
        self.assertTrue(summary["frontend_policy"]["knowledge_base"]["show_document_metrics"])
        self.assertTrue(summary["frontend_policy"]["settings"]["show_summary"])

    def test_update_frontend_policy_persists_policy_and_writes_audit_log(self):
        updated = settings_admin_service.update_frontend_policy(
            {
                "knowledge_base": {
                    "intro_text": "Visible documents only",
                    "empty_state_text": "No documents",
                    "readonly_notice": "Read only",
                    "show_document_metrics": False,
                },
                "settings": {
                    "show_summary": True,
                    "show_runtime_overview": False,
                    "show_permission_notice": True,
                    "readonly_notice": "Contact admin",
                },
            },
            actor_id="admin-1",
        )

        self.assertFalse(updated["knowledge_base"]["show_document_metrics"])
        on_disk = json.loads(self.policy_path.read_text(encoding="utf-8"))
        self.assertFalse(on_disk["knowledge_base"]["show_document_metrics"])
        entries = [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(entries[-1]["action"], "update_frontend_policy")

    def test_update_runtime_params_rejects_invalid_overlap(self):
        with self.assertRaises(SettingsAdminValidationError):
            settings_admin_service.update_runtime_params(
                {
                    "chunk_size": 300,
                    "chunk_overlap": 300,
                    "top_k": 5,
                    "similarity_threshold": 0.3,
                    "enable_cache": True,
                    "enable_rerank": True,
                    "enable_hybrid": True,
                    "enable_self_rag": False,
                }
            )

    def test_update_frontend_policy_rejects_unknown_fields(self):
        with self.assertRaises(SettingsAdminValidationError):
            settings_admin_service.update_frontend_policy(
                {
                    "knowledge_base": {
                        "intro_text": "ok",
                        "empty_state_text": "ok",
                        "readonly_notice": "ok",
                        "show_document_metrics": True,
                        "unexpected_flag": True,
                    },
                    "settings": {
                        "show_summary": True,
                        "show_runtime_overview": True,
                        "show_permission_notice": True,
                        "readonly_notice": "ok",
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
