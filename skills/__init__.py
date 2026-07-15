"""
Skills 模块

提供智能客服系统的技能框架，包括：
- 销售技能 (SalesAgentSkill)
- 技术支持技能 (TechSupportSkill)
- 议价技能 (NegotiationSkill)
- 客户分类技能 (CustomerClassifierSkill)
- 聊天技能 (ChatSkill)

架构设计：
1. BaseSkill: 技能基类，定义统一接口
2. SkillRegistry: 技能注册表，管理技能发现和调用
3. SkillManager: 技能管理器，协调多个技能协同工作
4. SkillsDataLoader: 数据加载器，加载产品知识等数据

使用示例：
    from skills import SkillManager, SkillResult

    manager = SkillManager()
    result = await manager.process({
        "query": "X12 Pro多少钱？",
        "history": [],
        "rag_results": documents
    })
"""

from skills.base import BaseSkill, SkillConfig, SkillResult, SkillType
from skills.registry import SkillRegistry
from skills.manager import SkillManager, skill_manager
from skills.data_loader import SkillsDataLoader

# 导入具体技能实现
from skills.skills import (
    SalesAgentSkill,
    TechSupportSkill,
    NegotiationSkill,
    CustomerClassifierSkill,
    ChatSkill
)

__all__ = [
    # 基类和配置
    "BaseSkill",
    "SkillConfig",
    "SkillResult",
    "SkillType",
    # 注册表和管理器
    "SkillRegistry",
    "SkillManager",
    "skill_manager",
    # 数据加载
    "SkillsDataLoader",
    # 具体技能
    "SalesAgentSkill",
    "TechSupportSkill",
    "NegotiationSkill",
    "CustomerClassifierSkill",
    "ChatSkill",
]

__version__ = "1.0.0"
