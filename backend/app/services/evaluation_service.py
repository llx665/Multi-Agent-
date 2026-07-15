"""
评测服务
提供 Agent 输出的多维度评测能力
"""

import sys
import os
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from evaluation.evaluator import ResponseEvaluator, response_evaluator
from evaluation.tracker import EvaluationTracker, evaluation_tracker


class EvaluationService:
    """
    评测服务

    功能：
    1. 对 Agent 输出进行多维度评测
    2. 记录评测报告
    3. 生成会话统计
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.evaluator = response_evaluator
        self.tracker = evaluation_tracker
        print("[EvaluationService] 初始化完成")

    def evaluate_response(
        self,
        session_id: str,
        query: str,
        response: str,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        评测单次 Agent 输出

        Args:
            session_id: 会话 ID
            query: 用户问题
            response: Agent 回复
            context: 上下文信息

        Returns:
            评测报告
        """
        context = context or {}
        context["session_id"] = session_id

        # 执行评测
        report = self.evaluator.evaluate(query, response, context)

        # 记录报告
        self.tracker.record_evaluation(report)

        return report.to_dict()

    def get_session_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话评测报告

        Args:
            session_id: 会话 ID

        Returns:
            报告字典
        """
        report = self.tracker.get_evaluation_report(session_id)
        if report:
            return report.to_dict()

        stats = self.tracker.get_session_statistics(session_id)
        global_stats = self.tracker.get_global_statistics()

        return {
            "session_id": session_id,
            "statistics": stats,
            "global_stats": global_stats
        }

    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计"""
        return self.tracker.get_global_statistics()

    def export_session_markdown(self, session_id: str, output_path: str = None) -> str:
        """
        导出会话报告为 Markdown

        Args:
            session_id: 会话 ID
            output_path: 输出文件路径

        Returns:
            Markdown 内容
        """
        return self.tracker.export_session_report(session_id, output_path)


# 全局单例
evaluation_service = EvaluationService()
