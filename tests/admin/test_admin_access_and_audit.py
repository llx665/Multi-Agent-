import json
import shutil
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.admin_main import app
from app.services.audit_log_service import AuditLogService
from app.services.auth_service import auth_service
from app.services.task_queue_service import task_queue_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "admin-access-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class AdminAccessAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        self.client = TestClient(app)
        self.user = auth_service.register("plain.user", "password123")
        self.admin = auth_service.register("admin.user", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.user_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.user['id'], self.user['username'])['token']}"
        }
        self.admin_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.admin['id'], self.admin['username'])['token']}"
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_plain_user_cannot_open_admin_dashboard(self):
        response = self.client.get("/api/admin/dashboard/summary", headers=self.user_headers)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_open_admin_dashboard(self):
        response = self.client.get("/api/admin/dashboard/summary", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_user"]["role"], "admin")

    def test_admin_can_read_task_status(self):
        task = task_queue_service.enqueue(
            task_type="knowledge_reload",
            payload={},
            actor_id=self.admin["id"],
            idempotency_key=f"test-admin-task-status:{uuid.uuid4().hex}",
        )

        response = self.client.get(f"/api/admin/tasks/{task['task_id']}", headers=self.admin_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], task["task_id"])
        self.assertEqual(response.json()["status"], "queued")

    def test_audit_log_service_appends_entries(self):
        log_path = self.temp_dir / "audit-log.jsonl"
        service = AuditLogService(storage_path=str(log_path))

        service.write(
            actor_id=self.admin["id"],
            module="dashboard",
            action="view",
            target_type="summary",
            target_id="root",
            result="success",
        )

        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["module"], "dashboard")
        self.assertEqual(entries[0]["result"], "success")


if __name__ == "__main__":
    unittest.main()
