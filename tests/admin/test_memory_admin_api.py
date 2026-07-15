import json
import shutil
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.admin_main import app
from app.services.auth_service import auth_service
from app.services.memory_admin_service import memory_admin_service
from core.session_context import session_context_manager


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "memory-admin-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class MemoryAdminApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir = self.temp_dir / "session_context"
        self.long_term_dir = self.temp_dir / "long_term"
        self.audit_log_path = self.temp_dir / "audit-log.jsonl"
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.long_term_dir.mkdir(parents=True, exist_ok=True)

        db_path = self.temp_dir / "auth.sqlite3"
        auth_service.reconfigure(database_url=f"sqlite:///{db_path.as_posix()}")
        memory_admin_service.reconfigure(
            context_storage_path=str(self.context_dir),
            long_term_storage_path=str(self.long_term_dir),
            audit_storage_path=str(self.audit_log_path),
        )
        session_context_manager._sessions.clear()
        session_context_manager._user_sessions.clear()

        self.client = TestClient(app)
        self.admin = auth_service.register("memory.admin", "password123")
        auth_service.update_user_role(self.admin["id"], "admin")
        self.user = auth_service.register("plain.user", "password123")
        self.focus_user = auth_service.register("focus.user", "password123")
        self.other_user = auth_service.register("other.user", "password123")

        self.admin_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.admin['id'], self.admin['username'])['token']}"
        }
        self.user_headers = {
            "Authorization": f"Bearer {auth_service.create_token(self.user['id'], self.user['username'])['token']}"
        }

        self._write_context(
            self.focus_user["id"],
            {
                "session_id": "session-focus",
                "updated_at": "2026-04-14T12:00:00",
                "turn_history": [{"role": "user", "content": "focus"}],
                "three_tier_summary": {"stats": {"short_term_turns": 1, "compressed_memories": 1}},
            },
        )
        self._write_profile(
            self.focus_user["id"],
            {
                "user_id": self.focus_user["id"],
                "preferences": {"industry": "retail"},
                "preference_meta": {"industry": {"source": "explicit_feedback", "confidence": 0.9}},
                "preference_history": [],
                "preference_conflicts": [],
                "interaction_history": [],
                "discussed_entities": [],
                "satisfaction_scores": [],
                "created_at": "2026-04-14T11:00:00",
                "last_updated": "2026-04-14T12:00:00",
            },
        )
        self._write_context(
            self.other_user["id"],
            {
                "session_id": "session-other",
                "updated_at": "2026-04-14T12:05:00",
                "turn_history": [{"role": "user", "content": "other"}],
                "three_tier_summary": {"stats": {"short_term_turns": 1, "compressed_memories": 0}},
            },
        )

    def tearDown(self):
        session_context_manager._sessions.clear()
        session_context_manager._user_sessions.clear()
        memory_admin_service.reconfigure()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_context(self, user_id: str, payload: dict):
        (self.context_dir / f"{user_id}_context.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_profile(self, user_id: str, payload: dict):
        (self.long_term_dir / f"{user_id}_profile.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_plain_user_cannot_list_memory_users(self):
        response = self.client.get("/api/admin/memory/users", headers=self.user_headers)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_filter_memory_users_by_query(self):
        response = self.client.get(
            "/api/admin/memory/users",
            params={"query": "focus"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["users"][0]["user_id"], self.focus_user["id"])

    def test_update_preference_writes_audit_log(self):
        response = self.client.post(
            f"/api/admin/memory/users/{self.focus_user['id']}/preferences",
            json={"key": "preferred_channel", "value": "wechat", "confidence": 0.8},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        entries = [
            json.loads(line)
            for line in self.audit_log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["actor_id"], self.admin["id"])
        self.assertEqual(entries[0]["module"], "memory")
        self.assertEqual(entries[0]["action"], "update_preference")
        self.assertEqual(entries[0]["target_id"], self.focus_user["id"])
        self.assertEqual(entries[0]["result"], "success")


if __name__ == "__main__":
    unittest.main()
