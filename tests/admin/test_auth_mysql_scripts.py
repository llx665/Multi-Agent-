import unittest
from unittest.mock import patch

from backend.scripts.migrate_auth_sqlite_to_mysql import main as migrate_main
from backend.scripts.seed_auth_users import main as seed_main


class AuthMySQLScriptsTest(unittest.TestCase):
    @patch("backend.scripts.migrate_auth_sqlite_to_mysql.migrate_sqlite_users")
    def test_migrate_script_passes_source_and_database_url(self, migrate_mock):
        migrate_mock.return_value = {"scanned": 2, "migrated": 2, "skipped": 0}
        code = migrate_main(
            [
                "--source",
                "data/auth/app.db",
                "--database-url",
                "mysql+pymysql://root:pass@127.0.0.1:3306/testdb?charset=utf8mb4",
            ]
        )
        self.assertEqual(code, 0)
        migrate_mock.assert_called_once_with(
            "data/auth/app.db",
            "mysql+pymysql://root:pass@127.0.0.1:3306/testdb?charset=utf8mb4",
        )

    @patch("backend.scripts.seed_auth_users.ensure_seed_users")
    def test_seed_script_passes_database_url_and_password(self, seed_mock):
        seed_mock.return_value = {"created": 4, "updated": 0, "total_seed_users": 4}
        code = seed_main(
            [
                "--database-url",
                "mysql+pymysql://root:pass@127.0.0.1:3306/testdb?charset=utf8mb4",
                "--password",
                "ChangeMe123!",
            ]
        )
        self.assertEqual(code, 0)
        seed_mock.assert_called_once_with(
            "mysql+pymysql://root:pass@127.0.0.1:3306/testdb?charset=utf8mb4",
            seed_password="ChangeMe123!",
        )


if __name__ == "__main__":
    unittest.main()
