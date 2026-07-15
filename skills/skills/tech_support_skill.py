"""
技术支持Skill
处理产品使用指导、故障排查等技术相关场景

数据来源：
- 技术支持知识库从 data/skills_data/tech_support_kb.yaml 加载
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from loguru import logger

from ..base import BaseSkill, SkillConfig, SkillResult, SkillType
from ..data_loader import skills_data_loader


class TechSupportSkill(BaseSkill):
    """技术支持Skill"""

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)
        self._data_loader = skills_data_loader

    def _get_kb(self) -> Dict[str, Any]:
        """获取技术支持知识库（懒加载）"""
        return self._data_loader.get_tech_support_kb()

    def _get_default_config(self) -> SkillConfig:
        return SkillConfig(
            name="tech_support",
            description="处理产品使用指导、故障排查、技术问题等场景。当用户遇到问题、咨询使用方法时激活。",
            skill_type=SkillType.TECHNICAL,
            priority=10
        )

    def should_activate(self, context: Dict[str, Any]) -> bool:
        """判断是否应该激活"""
        query = context.get("query", "").lower()

        tech_keywords = [
            "怎么用", "如何使用", "坏了", "故障", "问题",
            "错误", "不能", "无法", "卡", "慢", "热",
            "连不上", "闪退", "打不开", "充电", "没声音"
        ]

        return any(keyword in query for keyword in tech_keywords)

    def _classify_issue(self, query: str, rag_results: List[Dict] = None) -> str:
        """
        分类问题类型

        Args:
            query: 用户查询
            rag_results: RAG 检索结果

        Returns:
            问题类型
        """
        query_lower = query.lower()

        # 优先从 RAG 结果中判断问题类型
        if rag_results:
            for doc in rag_results:
                content = doc.get("content", "").lower()
                for issue_type, kb_info in self._get_kb().items():
                    for keyword in kb_info["keywords"]:
                        if keyword in content:
                            return issue_type

        # 从 query 中匹配关键词
        best_match = None
        best_score = 0

        for issue_type, kb_info in self._get_kb().items():
            score = 0
            for keyword in kb_info["keywords"]:
                if keyword in query_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = issue_type

        return best_match if best_match else "usage_guidance"

    def _query_knowledge_base(
        self,
        issue_type: str,
        rag_results: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        从知识库查询解决方案

        Args:
            issue_type: 问题类型
            rag_results: RAG 检索结果

        Returns:
            包含解决方案的字典
        """
        kb_entry = self._get_kb().get(issue_type, self._get_kb()["usage_guidance"])

        solutions = kb_entry.get("solutions", [])
        need_more_info = kb_entry.get("need_more_info", [])

        # 如果有 RAG 结果，从中提取相关信息补充
        supplementary = []
        if rag_results:
            for doc in rag_results:
                content = doc.get("content", "")
                # 从 FAQ 等文档中提取相关内容
                if self._is_relevant_faq(content, issue_type):
                    supplementary.append(self._extract_solution_from_faq(content))

        return {
            "issue_type": issue_type,
            "solutions": solutions + [s for s in supplementary if s],
            "need_more_info": need_more_info,
            "source": "knowledge_base"
        }

    def _is_relevant_faq(self, content: str, issue_type: str) -> bool:
        """判断 FAQ 内容是否与问题类型相关"""
        content_lower = content.lower()
        kb_entry = self._get_kb().get(issue_type, self._get_kb()["usage_guidance"])

        for keyword in kb_entry["keywords"]:
            if keyword in content_lower:
                return True
        return False

    def _extract_solution_from_faq(self, content: str) -> Optional[str]:
        """从 FAQ 格式的文本中提取解决方案"""
        # FAQ 通常是 Q:... A:... 格式
        if "A:" in content or "答：" in content:
            # 提取回答部分
            lines = content.split("\n")
            answer_lines = []
            capture = False
            for line in lines:
                if "A:" in line or "答：" in line:
                    capture = True
                    answer_lines.append(line.split(":", 1)[-1].split("答：", 1)[-1])
                elif capture and (line.startswith("Q") or line.startswith("问题")):
                    break
                elif capture:
                    answer_lines.append(line)
            if answer_lines:
                return " ".join(answer_lines).strip()
        return None

    def _generate_troubleshooting_steps(
        self,
        issue_type: str,
        solutions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        生成故障排查步骤

        Args:
            issue_type: 问题类型
            solutions: 解决方案列表

        Returns:
            步骤列表
        """
        steps = []
        for i, solution in enumerate(solutions[:5], 1):  # 最多5步
            steps.append({
                "step": i,
                "action": solution,
                "expected_result": self._get_expected_result(issue_type, i)
            })
        return steps

    def _get_expected_result(self, issue_type: str, step: int) -> str:
        """获取每步的预期结果"""
        results = {
            "hardware_issue": "设备正常启动或问题缓解",
            "performance_issue": "设备运行流畅，发热/耗电改善",
            "software_issue": "应用正常运行，不再闪退",
            "network_issue": "成功连接网络，信号正常",
            "usage_guidance": "完成所需操作",
            "accessory_issue": "充电正常或声音恢复正常"
        }
        return results.get(issue_type, "问题解决")

    def _format_tech_response(
        self,
        solutions: List[str],
        steps: List[Dict],
        need_more_info: List[str]
    ) -> str:
        """
        格式化技术支持回复

        Args:
            solutions: 解决方案列表
            steps: 排查步骤
            need_more_info: 需要补充的信息

        Returns:
            格式化回复文本
        """
        if not solutions and not steps:
            return "抱歉，我暂时没有找到针对您问题的解决方案。建议您联系我们的客服获取专业帮助。"

        response_parts = []

        if steps:
            response_parts.append("请按以下步骤操作：\n")
            for step in steps:
                response_parts.append(
                    f"【第{step['step']}步】{step['action']}\n"
                    f"   预期结果：{step['expected_result']}"
                )

        if need_more_info:
            response_parts.append(
                f"\n为了更好帮助您，能否提供以下信息：\n"
                f"  • {'、'.join(need_more_info[:3])}"
            )

        response_parts.append("\n如果问题仍未解决，请联系人工客服获得进一步帮助。")

        return "\n".join(response_parts)

    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行技术支持

        从知识库查询解决方案，生成故障排查步骤
        """
        try:
            query = context.get("query", "")
            rag_results = context.get("rag_results", [])

            # 1. 问题分类
            issue_type = self._classify_issue(query, rag_results)
            logger.info(f"[TechSupport] 问题分类: {issue_type}")

            # 2. 查询知识库
            kb_result = self._query_knowledge_base(issue_type, rag_results)
            solutions = kb_result.get("solutions", [])
            need_more_info = kb_result.get("need_more_info", [])

            # 3. 生成排查步骤
            steps = self._generate_troubleshooting_steps(issue_type, solutions)

            # 4. 计算评估分数
            evaluation_score = self._calculate_evaluation_score(
                query=query,
                issue_type=issue_type,
                solutions=solutions,
                steps=steps,
                rag_results=rag_results
            )

            response_data = {
                "intent": "tech_support",
                "issue_type": issue_type,
                "solutions": solutions,
                "troubleshooting_steps": steps,
                "need_more_info": need_more_info,
                "formatted_response": self._format_tech_response(solutions, steps, need_more_info),
                "follow_up_needed": True
            }

            logger.info(f"[TechSupport] 生成 {len(steps)} 个排查步骤")

            return SkillResult(
                success=True,
                data=response_data,
                message=f"技术支持方案已生成（问题类型：{issue_type}）",
                confidence=0.85 if solutions else 0.5,
                evaluation_score=evaluation_score
            )

        except Exception as e:
            logger.error(f"技术支持Skill执行失败: {str(e)}")
            return SkillResult(
                success=False,
                error=str(e),
                evaluation_score=0.0
            )

    def _calculate_evaluation_score(
        self,
        query: str,
        issue_type: str,
        solutions: List[str],
        steps: List[Dict],
        rag_results: List[Dict]
    ) -> float:
        """
        计算 Skill 输出质量评分

        评分维度：
        - 问题分类准确度
        - 解决方案相关性
        - RAG 召回率
        - 步骤完整性
        """
        score = 0.5  # 基础分

        # 问题分类准确
        if issue_type != "usage_guidance" or any(
            kw in query.lower()
            for kb_info in self._get_kb().values()
            for kw in kb_info["keywords"]
        ):
            score += 0.15

        # 有解决方案
        if solutions:
            score += 0.1

        # 步骤完整
        if steps and len(steps) >= 2:
            score += 0.1

        # RAG 结果有效利用
        if rag_results and any(r.get("similarity_score", 0) > 0.5 for r in rag_results):
            score += 0.1

        # 解决方案数量合理
        if 2 <= len(solutions) <= 5:
            score += 0.05

        return min(score, 1.0)

    def get_prompt(self) -> str:
        """获取技术支持专用提示词"""
        return """你是一个专业的技术支持工程师。要点：
1. 耐心倾听客户描述的问题，引导客户提供关键信息（型号、环境、操作步骤）
2. 按照排查步骤逐步指导，不要跳跃
3. 每一步都说明预期结果，让客户确认后再进行下一步
4. 如果问题复杂，及时升级给人工客服
5. 记录问题以便改进产品知识库"""
