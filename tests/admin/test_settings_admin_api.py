import shutil
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.admin_main import app
from app.services.auth_service import auth_service
from app.services.rag_runtime import rag_params_manager
from app.services.settings_admin_service import settings_admin_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "settings-admin-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class SettingsAdminApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.temp_dir / "auth.sqlite3"
        self.policy_path = self.temp_dir / "frontend_policy.json"
        self.audit_path = self.temp_dir / "admin_audit.jsonl"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        settings_admin_service.reconfigure(
            frontend_policy_path=str(self.policy_path),
            audit_storage_path=str(self.audit_path),
        )
        self.original_params = rag_params_manager.get_params()
        self.client = TestClient(app)

        self.admin = auth_service.register("settings.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.user = auth_service.register("settings.user", "password123")

        self.admin_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.admin['id'], self.admin['username'])['token']}"
        }
        self.user_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.user['id'], self.user['username'])['token']}"
        }

    def tearDown(self):
        rag_params_manager.update_params(self.original_params)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_admin_can_read_settings_summary(self):
        response = self.client.get("/api/admin/settings/summary", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("runtime_params", payload)
        self.assertIn("roles", payload["permission_model"])
        self.assertIn("super_admin", payload["permission_model"]["roles"])

    def test_plain_user_cannot_update_runtime_settings(self):
        response = self.client.post(
            "/api/admin/settings/runtime",
            json=self.original_params,
            headers=self.user_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_update_runtime_settings(self):
        next_params = {**self.original_params, "chunk_size": 520, "top_k": 7}
        response = self.client.post(
            "/api/admin/settings/runtime",
            json=next_params,
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["params"]["chunk_size"], 520)
        self.assertEqual(rag_params_manager.get_params()["chunk_size"], 520)

    def test_admin_can_update_frontend_policy(self):
        response = self.client.post(
            "/api/admin/settings/frontend-policy",
            json={
                "knowledge_base": {
                    "intro_text": "Visible docs only",
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
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["policy"]["knowledge_base"]["show_document_metrics"])

    def test_invalid_runtime_settings_returns_400(self):
        response = self.client.post(
            "/api/admin/settings/runtime",
            json={**self.original_params, "chunk_size": 200, "chunk_overlap": 200},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_frontend_policy_returns_400(self):
        response = self.client.post(
            "/api/admin/settings/frontend-policy",
            json={
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
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
