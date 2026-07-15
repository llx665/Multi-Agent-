import shutil
import unittest
import uuid
from pathlib import Path

from app.services.auth_service import AuthService


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "auth-mysql-service-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class AuthMySQLServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.temp_dir / "auth.sqlite3"
        self.service = AuthService(database_url=f"sqlite:///{self.db_path.as_posix()}")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mysql_schema_uses_mysql_safe_primary_key(self):
        sql = self.service._users_table_sql("mysql")
        self.assertIn("id VARCHAR(64) NOT NULL", sql)
        self.assertIn("PRIMARY KEY (id)", sql)
        self.assertIn("UNIQUE KEY uk_users_username (username)", sql)
        self.assertNotIn("id TEXT PRIMARY KEY", sql)

    def test_list_user_records_returns_password_fields_for_migration(self):
        created = self.service.register("schema.user", "password123")
        rows = self.service.list_user_records()
        row = next(item for item in rows if item["id"] == created["id"])
        self.assertEqual(row["username"], "schema.user")
        self.assertIn("password_salt", row)
        self.assertIn("password_hash", row)
        self.assertEqual(row["role"], "user")

    def test_create_user_record_preserves_existing_id_role_and_status(self):
        record = {
            "id": "usr_external_0001",
            "username": "external.user",
            "password_salt": "salt-1",
            "password_hash": "hash-1",
            "created_at": 1700000000,
            "status": "disabled",
            "role": "operator",
            "last_login_at": 1700000100,
            "password_updated_at": 1700000000,
            "updated_at": 1700000200,
        }
        created = self.service.create_user_record(record)
        self.assertEqual(created["id"], "usr_external_0001")
        stored = self.service.get_user_by_id("usr_external_0001")
        self.assertEqual(stored["username"], "external.user")
        self.assertEqual(stored["role"], "operator")
        self.assertEqual(stored["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
