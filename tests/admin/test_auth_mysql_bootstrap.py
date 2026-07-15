import shutil
import unittest
import uuid
from pathlib import Path

from app.services.auth_mysql_bootstrap import ensure_seed_users, migrate_sqlite_users
from app.services.auth_service import AuthError, AuthService


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "auth-mysql-bootstrap-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class AuthMySQLBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.source_db = self.temp_dir / "source.sqlite3"
        self.target_db = self.temp_dir / "target.sqlite3"
        self.source_service = AuthService(database_url=f"sqlite:///{self.source_db.as_posix()}")
        self.target_url = f"sqlite:///{self.target_db.as_posix()}"
        self.target_service = AuthService(database_url=self.target_url)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_migrate_sqlite_users_preserves_ids_roles_and_status(self):
        admin = self.source_service.register("legacy.admin", "password123")
        self.source_service.update_user_role(admin["id"], "admin")
        self.source_service.update_user_status(admin["id"], "disabled")
        user = self.source_service.register("legacy.user", "password123")

        stats = migrate_sqlite_users(str(self.source_db), self.target_url)

        reloaded = AuthService(database_url=self.target_url)
        users = {item["username"]: item for item in reloaded.list_users()}
        self.assertEqual(stats["scanned"], 2)
        self.assertEqual(stats["migrated"], 2)
        self.assertEqual(users["legacy.admin"]["id"], admin["id"])
        self.assertEqual(users["legacy.admin"]["role"], "admin")
        self.assertEqual(users["legacy.admin"]["status"], "disabled")
        self.assertEqual(users["legacy.user"]["id"], user["id"])

    def test_migrate_sqlite_users_raises_on_conflicting_existing_target_user(self):
        self.source_service.register("legacy.user", "password123")
        self.target_service.create_user_record(
            {
                "id": "usr_conflict_0001",
                "username": "legacy.user",
                "password_salt": "salt-x",
                "password_hash": "hash-x",
                "created_at": 1700000000,
                "status": "active",
                "role": "admin",
                "last_login_at": None,
                "password_updated_at": 1700000000,
                "updated_at": 1700000000,
            }
        )

        with self.assertRaisesRegex(AuthError, "conflicts with existing target user"):
            migrate_sqlite_users(str(self.source_db), self.target_url)

    def test_ensure_seed_users_creates_all_missing_accounts(self):
        stats = ensure_seed_users(self.target_url, seed_password="ChangeMe123!")

        reloaded = AuthService(database_url=self.target_url)
        users = {item["username"]: item for item in reloaded.list_users()}
        self.assertEqual(stats["created"], 4)
        self.assertEqual(users["super_admin1"]["role"], "super_admin")
        self.assertEqual(users["admin1"]["role"], "admin")
        self.assertEqual(users["operator1"]["role"], "operator")
        self.assertEqual(users["user1"]["role"], "user")

    def test_ensure_seed_users_preserves_existing_password_while_repairing_role_and_status(self):
        existing = self.target_service.register("admin1", "OriginalPass123!")
        self.target_service.update_user_role(existing["id"], "user")
        self.target_service.update_user_status(existing["id"], "disabled")

        stats = ensure_seed_users(self.target_url, seed_password="ChangeMe123!")

        reloaded = AuthService(database_url=self.target_url)
        repaired = reloaded.get_user_by_id(existing["id"])
        self.assertEqual(stats["created"], 3)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(repaired["role"], "admin")
        self.assertEqual(repaired["status"], "active")
        self.assertEqual(reloaded.authenticate("admin1", "OriginalPass123!")["id"], existing["id"])
        with self.assertRaises(AuthError):
            reloaded.authenticate("admin1", "ChangeMe123!")


if __name__ == "__main__":
    unittest.main()
