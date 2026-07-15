"""
Skill基类
定义所有Skill的标准接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class SkillType(Enum):
    """Skill类型枚举"""
    SALES = "sales"                    # 销售相关
    TECHNICAL = "technical"            # 技术支持
    COMPLAINT = "complaint"            # 投诉处理
    NEGOTIATION = "negotiation"        # 价格谈判
    PRODUCT = "product"                # 产品知识
    CUSTOMER = "customer"              # 客户分析
    GENERAL = "general"               # 通用技能


@dataclass
class SkillResult:
    """Skill执行结果"""
    success: bool
    data: Any = None
    message: str = ""
    error: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    evaluation_score: float = 0.0  # Skill 输出质量评分 (0.0-1.0)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp.isoformat(),
            "evaluation_score": self.evaluation_score
        }


@dataclass
class SkillConfig:
    """Skill配置"""
    name: str
    description: str
    skill_type: SkillType = SkillType.GENERAL
    enabled: bool = True
    priority: int = 0  # 优先级，数字越大优先级越高
    timeout: int = 30  # 超时时间（秒）
    max_retries: int = 3  # 最大重试次数
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Skill基类，所有Skill必须继承此类"""

    def __init__(self, config: Optional[SkillConfig] = None):
        self.config = config or self._get_default_config()
        self._initialized = False

    @abstractmethod
    def _get_default_config(self) -> SkillConfig:
        """获取默认配置，子类必须实现"""
        pass

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行Skill逻辑，子类必须实现

        Args:
            context: 执行上下文，包含：
                - query: 用户查询
                - history: 对话历史
                - user_info: 用户信息
                - 其他自定义字段

        Returns:
            SkillResult: 执行结果
        """
        pass

    def initialize(self) -> None:
        """初始化Skill，只在Skill被加载时调用一次"""
        if not self._initialized:
            self._do_initialize()
            self._initialized = True

    def _do_initialize(self) -> None:
        """实际初始化逻辑，子类可重写"""
        pass

    def validate_context(self, context: Dict[str, Any]) -> bool:
        """验证上下文是否合法，子类可重写"""
        return True

    def get_prompt(self) -> Optional[str]:
        """获取Skill专用的提示词，子类可重写"""
        return None

    def should_activate(self, context: Dict[str, Any]) -> bool:
        """判断Skill是否应该被激活，子类可重写"""
        return True

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def description(self) -> str:
        return self.config.description

    @property
    def skill_type(self) -> SkillType:
        return self.config.skill_type

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} type={self.skill_type.value}>"
