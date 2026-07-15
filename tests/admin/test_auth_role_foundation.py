import shutil
import unittest
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth
from app.services.auth_service import auth_service
from app.services.permission_service import PermissionDenied, permission_service


test_app = FastAPI()
test_app.include_router(auth.router, prefix="/api/v1")
TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "admin-auth-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class AuthRoleFoundationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        self.client = TestClient(test_app)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_register_defaults_to_user_role(self):
        user = auth_service.register("phase1.user", "password123")
        stored = auth_service.get_user_by_id(user["id"])
        self.assertEqual(stored["role"], "user")
        self.assertEqual(stored["status"], "active")

    def test_permission_service_rejects_plain_user(self):
        with self.assertRaises(PermissionDenied):
            permission_service.require_any_role(
                {"id": "u1", "role": "user", "status": "active"},
                {"admin", "super_admin", "operator"},
            )

    def test_auth_me_returns_role_and_status(self):
        user = auth_service.register("phase1.viewer", "password123")
        token = auth_service.create_token(user["id"], user["username"])["token"]

        response = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "user")
        self.assertEqual(response.json()["status"], "active")


if __name__ == "__main__":
    unittest.main()
