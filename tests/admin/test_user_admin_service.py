import json
import shutil
import unittest
import uuid
from pathlib import Path

from app.services.auth_service import auth_service
from app.services.audit_log_service import AuditLogService
from app.services.user_admin_service import BadRequestError, ForbiddenError, NotFoundError, user_admin_service
import app.services.user_admin_service as user_admin_service_module


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "user-admin-service-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class UserAdminServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")

        self.audit_path = self.temp_dir / "admin_audit.jsonl"
        self.original_audit = user_admin_service_module.audit_log_service
        user_admin_service_module.audit_log_service = AuditLogService(storage_path=str(self.audit_path))

        self.super_admin = auth_service.register("svc.super.admin", "password123")
        auth_service.update_user_role(self.super_admin["id"], "super_admin")

        self.admin = auth_service.register("svc.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.admin_peer = auth_service.register("svc.admin.peer", "password123")
        auth_service.update_user_role(self.admin_peer["id"], "admin")

        self.operator = auth_service.register("svc.operator", "password123")
        auth_service.update_user_role(self.operator["id"], "operator")

        self.user = auth_service.register("svc.user", "password123")

    def tearDown(self):
        user_admin_service_module.audit_log_service = self.original_audit
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _read_audit_logs(self):
        if not self.audit_path.exists():
            return []
        with open(self.audit_path, "r", encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    def test_get_user_detail_returns_required_fields(self):
        detail = user_admin_service.get_user_detail(actor_role="admin", user_id=self.user["id"])

        self.assertEqual(detail["id"], self.user["id"])
        self.assertEqual(detail["username"], "svc.user")
        self.assertEqual(detail["role"], "user")
        self.assertEqual(detail["status"], "active")
        self.assertIn("created_at", detail)
        self.assertIn("updated_at", detail)
        self.assertIn("last_login_at", detail)
        self.assertIn("password_updated_at", detail)

    def test_admin_can_view_another_admin_detail(self):
        detail = user_admin_service.get_user_detail(actor_role="admin", user_id=self.admin_peer["id"])
        self.assertEqual(detail["id"], self.admin_peer["id"])
        self.assertEqual(detail["role"], "admin")

    def test_admin_can_disable_user_and_write_status_audit_log(self):
        updated = user_admin_service.update_status(
            actor_id=self.admin["id"],
            actor_role="admin",
            user_id=self.user["id"],
            status="disabled",
        )

        self.assertEqual(updated["status"], "disabled")
        stored = auth_service.get_user_by_id(self.user["id"])
        self.assertEqual(stored["status"], "disabled")

        logs = self._read_audit_logs()
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["action"], "update_status")
        self.assertEqual(log["target_id"], self.user["id"])
        self.assertEqual(log["extra"]["old_status"], "active")
        self.assertEqual(log["extra"]["new_status"], "disabled")

    def test_admin_cannot_disable_another_admin(self):
        with self.assertRaises(ForbiddenError):
            user_admin_service.update_status(
                actor_id=self.admin["id"],
                actor_role="admin",
                user_id=self.admin_peer["id"],
                status="disabled",
            )

    def test_cannot_update_own_status(self):
        with self.assertRaises(ForbiddenError):
            user_admin_service.update_status(
                actor_id=self.admin["id"],
                actor_role="admin",
                user_id=self.admin["id"],
                status="disabled",
            )

    def test_admin_cannot_modify_role(self):
        with self.assertRaises(ForbiddenError):
            user_admin_service.update_role(
                actor_id=self.admin["id"],
                actor_role="admin",
                user_id=self.user["id"],
                role="operator",
            )

    def test_super_admin_cannot_modify_own_role(self):
        with self.assertRaises(ForbiddenError):
            user_admin_service.update_role(
                actor_id=self.super_admin["id"],
                actor_role="super_admin",
                user_id=self.super_admin["id"],
                role="admin",
            )

    def test_get_user_detail_not_found_raises_not_found_error(self):
        with self.assertRaises(NotFoundError):
            user_admin_service.get_user_detail(actor_role="super_admin", user_id="usr_missing")

    def test_update_status_not_found_raises_not_found_error(self):
        with self.assertRaises(NotFoundError):
            user_admin_service.update_status(
                actor_id=self.super_admin["id"],
                actor_role="super_admin",
                user_id="usr_missing",
                status="disabled",
            )

    def test_invalid_status_raises_bad_request_error(self):
        with self.assertRaises(BadRequestError):
            user_admin_service.update_status(
                actor_id=self.super_admin["id"],
                actor_role="super_admin",
                user_id=self.user["id"],
                status="archived",
            )

    def test_invalid_role_raises_bad_request_error(self):
        with self.assertRaises(BadRequestError):
            user_admin_service.update_role(
                actor_id=self.super_admin["id"],
                actor_role="super_admin",
                user_id=self.user["id"],
                role="viewer",
            )


if __name__ == "__main__":
    unittest.main()
