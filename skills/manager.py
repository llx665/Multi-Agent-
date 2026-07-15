"""
Skill管理器
统一管理和协调所有Skill
"""

from typing import Dict, List, Optional, Any
from loguru import logger

from .base import BaseSkill, SkillConfig, SkillResult, SkillType
from .registry import SkillRegistry
from .data_loader import SkillsDataLoader
from .skills import (
    SalesAgentSkill,
    TechSupportSkill,
    NegotiationSkill,
    CustomerClassifierSkill,
    ChatSkill
)


class SkillManager:
    """Skill管理器，统一管理所有Skill"""

    def __init__(self):
        self.registry = SkillRegistry()
        self.loader = SkillsDataLoader()
        self._init_default_skills()
        self._context_cache = {}

    def _init_default_skills(self) -> None:
        """初始化默认Skill"""
        default_skills = [
            SalesAgentSkill(),
            TechSupportSkill(),
            NegotiationSkill(),
            CustomerClassifierSkill(),
            ChatSkill()
        ]

        for skill in default_skills:
            self.register(skill)
            logger.info(f"默认Skill已注册: {skill.name}")

    def register(self, skill: BaseSkill, config: Optional[SkillConfig] = None) -> None:
        """注册Skill"""
        self.registry.register(skill, config)

    def unregister(self, skill_name: str) -> bool:
        """注销Skill"""
        return self.registry.unregister(skill_name)

    def get(self, skill_name: str) -> Optional[BaseSkill]:
        """获取Skill"""
        return self.registry.get(skill_name)

    def list_skills(self) -> List[str]:
        """列出所有Skill"""
        return self.registry.list_skills()

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户输入，协调多个Skill

        Args:
            context: 包含query、history、rag_results等

        Returns:
            处理结果，包含：
                - selected_skill: 使用的Skill
                - result: Skill执行结果
                - customer_type: 客户类型（如果有）
                - response: 建议的回复
        """
        # 从 context 中提取 rag_results（如果有）
        rag_results = context.get("rag_results", [])

        # 先执行客户分类
        customer_result = await self.registry.execute("customer_classifier", context)
        customer_type = None
        if customer_result.success:
            customer_type = customer_result.data.get("customer_type")
            context["customer_type"] = customer_type

        # 获取当前激活的 Skills
        active_skills = self.registry.get_active_skills(context)

        results = {}
        for skill in active_skills:
            result = await self.registry.execute(skill.name, context)
            results[skill.name] = result

        primary_result = None
        primary_skill_name = None
        for skill_name, result in results.items():
            if result.success:
                primary_result = result
                primary_skill_name = skill_name
                break

        response_data = {
            "selected_skill": primary_skill_name,
            "customer_type": customer_type,
            "skill_results": {k: v.to_dict() for k, v in results.items()},
            "primary_result": primary_result.to_dict() if primary_result else None
        }

        return response_data

    def get_skill_prompt(self, skill_name: str) -> Optional[str]:
        """获取Skill的专用提示词"""
        skill = self.get(skill_name)
        if skill:
            return skill.get_prompt()
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.registry.get_statistics()


skill_manager = SkillManager()
