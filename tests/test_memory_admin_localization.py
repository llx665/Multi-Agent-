from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class MemoryAdminLocalizationTest(unittest.TestCase):
    def test_memory_admin_frontend_is_localized_to_chinese(self) -> None:
        content = read_text("frontend/src/admin/pages/MemoryAdminPage.vue")

        expected_texts = [
            "记忆管理",
            "面向运营的三层记忆工作台",
            "搜索用户 ID 或用户名",
            "最近会话",
            "短期记忆",
            "长期偏好",
            "清理全部记忆",
            "上下文元数据",
            "最近对话",
            "中期摘要",
        ]
        forbidden_texts = [
            "Memory Console",
            "Search user_id / username",
            "Refresh Users",
            "Username",
            "Latest Session",
            "Short Term",
            "Preferences",
            "Clear All Memory",
            "Long-Term Profile",
            "Context Metadata",
            "Recent Turns",
        ]

        for text in expected_texts:
            self.assertIn(text, content)

        for text in forbidden_texts:
            self.assertNotIn(text, content)

    def test_memory_admin_html_title_is_localized(self) -> None:
        content = read_text("frontend/admin.html")
        self.assertIn("<title>后台管理系统</title>", content)

    def test_memory_admin_api_messages_are_localized(self) -> None:
        content = read_text("backend/app/api/admin/memory.py")
        self.assertIn("未找到该用户的记忆数据", content)
        self.assertIn("清理上下文记忆失败", content)
        self.assertIn("清理全部记忆失败", content)


if __name__ == "__main__":
    unittest.main()
