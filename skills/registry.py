"""
Skill注册表
管理和协调所有注册的Skill
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

from .base import BaseSkill, SkillConfig, SkillResult, SkillType


class SkillRegistry:
    """Skill注册表，管理所有Skill的生命周期"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._skill_configs: Dict[str, SkillConfig] = {}
        self._execution_history: List[Dict] = []

    def register(self, skill: BaseSkill, config: Optional[SkillConfig] = None) -> None:
        """注册一个Skill

        Args:
            skill: Skill实例
            config: 可选的配置，会覆盖skill的默认配置
        """
        skill_name = skill.name

        if config:
            skill.config = config
            self._skill_configs[skill_name] = config

        skill.initialize()
        self._skills[skill_name] = skill
        logger.info(f"Skill注册成功: {skill_name}")

    def unregister(self, skill_name: str) -> bool:
        """注销一个Skill

        Args:
            skill_name: Skill名称

        Returns:
            bool: 是否成功注销
        """
        if skill_name in self._skills:
            del self._skills[skill_name]
            logger.info(f"Skill已注销: {skill_name}")
            return True
        return False

    def get(self, skill_name: str) -> Optional[BaseSkill]:
        """获取一个Skill

        Args:
            skill_name: Skill名称

        Returns:
            Optional[BaseSkill]: Skill实例
        """
        return self._skills.get(skill_name)

    def list_skills(self) -> List[str]:
        """列出所有已注册的Skill名称"""
        return list(self._skills.keys())

    def list_skills_by_type(self, skill_type: SkillType) -> List[BaseSkill]:
        """获取指定类型的所有Skill

        Args:
            skill_type: Skill类型

        Returns:
            List[BaseSkill]: 匹配类型的Skill列表
        """
        return [s for s in self._skills.values() if s.skill_type == skill_type]

    def get_active_skills(self, context: Dict[str, Any]) -> List[BaseSkill]:
        """获取当前上下文中应该激活的Skill

        Args:
            context: 执行上下文

        Returns:
            List[BaseSkill]: 应该激活的Skill列表，按优先级排序
        """
        active = []

        for skill in self._skills.values():
            if not skill.config.enabled:
                continue
            if skill.should_activate(context):
                active.append(skill)

        return sorted(active, key=lambda s: s.config.priority, reverse=True)

    async def execute(self, skill_name: str, context: Dict[str, Any]) -> SkillResult:
        """执行指定的Skill

        Args:
            skill_name: Skill名称
            context: 执行上下文

        Returns:
            SkillResult: 执行结果
        """
        skill = self.get(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Skill不存在: {skill_name}"
            )

        start_time = datetime.now()

        try:
            if not skill.validate_context(context):
                return SkillResult(
                    success=False,
                    error="上下文验证失败"
                )

            result = await skill.execute(context)
            result.execution_time = (datetime.now() - start_time).total_seconds()

            self._record_execution(skill_name, context, result)
            return result

        except Exception as e:
            logger.error(f"Skill执行失败 {skill_name}: {str(e)}")
            return SkillResult(
                success=False,
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds()
            )

    async def execute_best_match(self, context: Dict[str, Any]) -> SkillResult:
        """执行最适合当前上下文的Skill

        Args:
            context: 执行上下文

        Returns:
            SkillResult: 最佳匹配Skill的执行结果
        """
        active_skills = self.get_active_skills(context)

        if not active_skills:
            return SkillResult(
                success=False,
                error="没有找到合适的Skill"
            )

        best_skill = active_skills[0]
        logger.info(f"选择Skill: {best_skill.name}")

        return await self.execute(best_skill.name, context)

    def _record_execution(self, skill_name: str, context: Dict, result: SkillResult) -> None:
        """记录执行历史"""
        self._execution_history.append({
            "skill_name": skill_name,
            "timestamp": datetime.now().isoformat(),
            "success": result.success,
            "execution_time": result.execution_time
        })

        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-1000:]

    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """获取执行历史"""
        return self._execution_history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self._execution_history)
        if total == 0:
            return {"total_executions": 0}

        successful = sum(1 for h in self._execution_history if h["success"])
        avg_time = sum(h["execution_time"] for h in self._execution_history) / total

        return {
            "total_executions": total,
            "success_rate": successful / total,
            "average_execution_time": avg_time,
            "registered_skills": len(self._skills)
        }
