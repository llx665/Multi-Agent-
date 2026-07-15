import shutil
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.admin_main import app
from app.services.auth_service import auth_service


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "user-admin-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class UserAdminApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        self.client = TestClient(app)
        self.super_admin = auth_service.register("root.admin", "password123")
        auth_service.update_user_role(self.super_admin["id"], "super_admin")
        self.admin = auth_service.register("ops.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.admin_peer = auth_service.register("peer.admin", "password123")
        auth_service.update_user_role(self.admin_peer["id"], "admin")
        self.target = auth_service.register("managed.user", "password123")
        self.super_admin_headers = self._build_headers(self.super_admin)
        self.admin_headers = self._build_headers(self.admin)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _build_headers(self, user: dict) -> dict:
        token = auth_service.create_token(user["id"], user["username"])["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_list_users_returns_role_status_and_updated_at(self):
        response = self.client.get("/api/admin/users", headers=self.super_admin_headers)
        self.assertEqual(response.status_code, 200)
        users = response.json()["users"]
        target = next(item for item in users if item["user_id"] == self.target["id"])
        self.assertEqual(target["role"], "user")
        self.assertEqual(target["status"], "active")
        self.assertIn("updated_at", target)
        self.assertIsInstance(target["updated_at"], int)

    def test_get_user_detail(self):
        response = self.client.get(
            f"/api/admin/users/{self.target['id']}",
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["user_id"], self.target["id"])
        self.assertEqual(detail["username"], self.target["username"])
        self.assertEqual(detail["role"], "user")
        self.assertEqual(detail["status"], "active")
        self.assertIn("created_at", detail)
        self.assertIn("updated_at", detail)
        self.assertIn("last_login_at", detail)
        self.assertIn("password_updated_at", detail)
        self.assertIsNone(detail["last_login_at"])

    def test_admin_can_disable_normal_user(self):
        response = self.client.patch(
            f"/api/admin/users/{self.target['id']}/status",
            json={"status": "disabled"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "disabled")
        stored = auth_service.get_user_by_id(self.target["id"])
        self.assertEqual(stored["status"], "disabled")

    def test_admin_cannot_disable_admin(self):
        before = auth_service.get_user_by_id(self.admin_peer["id"])
        response = self.client.patch(
            f"/api/admin/users/{self.admin_peer['id']}/status",
            json={"status": "disabled"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 403)
        after = auth_service.get_user_by_id(self.admin_peer["id"])
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["updated_at"], before["updated_at"])

    def test_admin_cannot_disable_self(self):
        before = auth_service.get_user_by_id(self.admin["id"])
        response = self.client.patch(
            f"/api/admin/users/{self.admin['id']}/status",
            json={"status": "disabled"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 403)
        after = auth_service.get_user_by_id(self.admin["id"])
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["updated_at"], before["updated_at"])

    def test_super_admin_can_update_other_user_role(self):
        response = self.client.patch(
            f"/api/admin/users/{self.admin['id']}/role",
            json={"role": "operator"},
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "operator")
        stored = auth_service.get_user_by_id(self.admin["id"])
        self.assertEqual(stored["role"], "operator")

    def test_super_admin_cannot_update_own_role(self):
        before = auth_service.get_user_by_id(self.super_admin["id"])
        response = self.client.patch(
            f"/api/admin/users/{self.super_admin['id']}/role",
            json={"role": "admin"},
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 403)
        after = auth_service.get_user_by_id(self.super_admin["id"])
        self.assertEqual(after["role"], before["role"])
        self.assertEqual(after["updated_at"], before["updated_at"])

    def test_update_status_invalid_value_returns_400(self):
        response = self.client.patch(
            f"/api/admin/users/{self.target['id']}/status",
            json={"status": "paused"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_update_status_short_invalid_value_returns_400_not_422(self):
        response = self.client.patch(
            f"/api/admin/users/{self.target['id']}/status",
            json={"status": "x"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_update_role_invalid_value_returns_400(self):
        response = self.client.patch(
            f"/api/admin/users/{self.target['id']}/role",
            json={"role": "invalid_role"},
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_update_role_short_invalid_value_returns_400_not_422(self):
        response = self.client.patch(
            f"/api/admin/users/{self.target['id']}/role",
            json={"role": "x"},
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_get_user_detail_not_found_returns_404(self):
        response = self.client.get(
            "/api/admin/users/usr_not_exists_1234",
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_update_status_target_user_not_found_returns_404(self):
        response = self.client.patch(
            "/api/admin/users/usr_not_exists_1234/status",
            json={"status": "disabled"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_update_role_target_user_not_found_returns_404(self):
        response = self.client.patch(
            "/api/admin/users/usr_not_exists_1234/role",
            json={"role": "operator"},
            headers=self.super_admin_headers,
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
