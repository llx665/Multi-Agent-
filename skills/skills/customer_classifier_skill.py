"""
客户分类Skill
识别客户类型，指导后续服务策略
"""

import asyncio
from typing import Any, Dict
from enum import Enum
from loguru import logger

from ..base import BaseSkill, SkillConfig, SkillResult, SkillType


class CustomerType(Enum):
    """客户类型枚举"""
    RATIONAL = "rational"           # 理性客户
    PRICE_SENSITIVE = "price_sensitive"  # 价格敏感型
    EMOTIONAL = "emotional"        # 情感型
    HESITANT = "hesitant"         # 犹豫型
    URGENT = "urgent"             # 急于购买型
    DIFFICULT = "difficult"       # 难缠型


class CustomerClassifierSkill(BaseSkill):
    """客户分类Skill"""

    def _get_default_config(self) -> SkillConfig:
        return SkillConfig(
            name="customer_classifier",
            description="识别客户类型（理性型、价格敏感型、难缠型等），优化服务策略。始终激活，为其他Skill提供决策支持。",
            skill_type=SkillType.CUSTOMER,
            priority=20
        )

    def should_activate(self, context: Dict[str, Any]) -> bool:
        """始终激活，为其他Skill提供参考"""
        return True

    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行客户分类"""
        try:
            query = context.get("query", "")
            history = context.get("history", [])
            all_text = query + " ".join([h.get("content", "") for h in history])

            customer_type = self._classify(all_text)
            service_strategy = self._get_strategy(customer_type)

            response = {
                "customer_type": customer_type.value,
                "confidence": 0.8,
                "strategy": service_strategy,
                "recommendations": self._get_recommendations(customer_type)
            }

            return SkillResult(
                success=True,
                data=response,
                message=f"客户类型识别为: {customer_type.value}",
                confidence=0.8
            )

        except Exception as e:
            logger.error(f"客户分类Skill执行失败: {str(e)}")
            return SkillResult(
                success=False,
                error=str(e)
            )

    def _classify(self, text: str) -> CustomerType:
        """分类客户类型"""
        text_lower = text.lower()

        if any(k in text_lower for k in ["太贵了", "能不能便宜", "便宜点", "贵"]):
            return CustomerType.PRICE_SENSITIVE
        elif any(k in text_lower for k in ["我就要这个", "现在就买", "快"]):
            return CustomerType.URGENT
        elif any(k in text_lower for k in ["再考虑", "回去想想", "不急"]):
            return CustomerType.HESITANT
        elif any(k in text_lower for k in ["不行", "不满意", "投诉", "找你们领导"]):
            return CustomerType.DIFFICULT
        elif any(k in text_lower for k in ["参数", "配置", "性能", "对比"]):
            return CustomerType.RATIONAL

        return CustomerType.EMOTIONAL

    def _get_strategy(self, customer_type: CustomerType) -> Dict[str, Any]:
        """获取服务策略"""
        strategies = {
            CustomerType.RATIONAL: {
                "approach": "专业、详细",
                "focus": "产品参数、性能对比",
                "tone": "严谨、专业"
            },
            CustomerType.PRICE_SENSITIVE: {
                "approach": "突出性价比",
                "focus": "优惠活动、赠品",
                "tone": "热情、实在"
            },
            CustomerType.EMOTIONAL: {
                "approach": "情感共鸣",
                "focus": "使用体验、生活品质",
                "tone": "温暖、亲切"
            },
            CustomerType.HESITANT: {
                "approach": "耐心解答",
                "focus": "消除顾虑、建立信任",
                "tone": "耐心、不催促"
            },
            CustomerType.URGENT: {
                "approach": "快速响应",
                "focus": "库存、立即购买",
                "tone": "干脆、利落"
            },
            CustomerType.DIFFICULT: {
                "approach": "稳住心态",
                "focus": "倾听、解决问题",
                "tone": "冷静、耐心"
            }
        }
        return strategies.get(customer_type, strategies[CustomerType.EMOTIONAL])

    def _get_recommendations(self, customer_type: CustomerType) -> list:
        """获取推荐建议"""
        recommendations = {
            CustomerType.RATIONAL: ["提供详细参数对比", "展示第三方评测", "邀请试用体验"],
            CustomerType.PRICE_SENSITIVE: ["强调限时优惠", "推荐高性价比款", "赠送配件"],
            CustomerType.EMOTIONAL: ["讲成功案例", "展示用户好评", "强调生活提升"],
            CustomerType.HESITANT: ["保持联系", "发送产品资料", "不催促"],
            CustomerType.URGENT: ["确认库存", "简化流程", "立即下单优惠"],
            CustomerType.DIFFICULT: ["认真倾听", "表示理解", "升级处理"]
        }
        return recommendations.get(customer_type, [])
