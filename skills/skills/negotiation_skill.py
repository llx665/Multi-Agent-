"""
价格谈判Skill
处理客户讨价还价、价格异议等场景

数据来源：
- 产品折扣数据从 data/skills_data/product_discounts.yaml 加载
"""

import asyncio
import re
from typing import Any, Dict, Optional
from loguru import logger

from ..base import BaseSkill, SkillConfig, SkillResult, SkillType
from ..data_loader import skills_data_loader


# 折扣层级配置（保持不变）
DISCOUNT_LEVELS = [
    {
        "level": 1,
        "name": "首次报价",
        "discount_rate": 0.90,  # 标价 × 0.9
        "description": "活动优惠价，可立即申请",
        "message": "您好，我可以帮您申请活动优惠价"
    },
    {
        "level": 2,
        "name": "二次优惠",
        "discount_rate": 0.85,  # 标价 × 0.85
        "description": "需要申请，适合诚意客户",
        "message": "我跟店长申请一下，给您一个更优惠的价格"
    },
    {
        "level": 3,
        "name": "最大优惠",
        "discount_rate": None,  # 使用 min_price
        "description": "底价，不能再低",
        "message": "这已经是我们的最大权限了，真的不能再低了"
    }
]


class NegotiationSkill(BaseSkill):
    """价格谈判Skill"""

    def __init__(self, config: Optional[SkillConfig] = None, data_loader: Optional[Any] = None):
        super().__init__(config)
        self._data_loader = data_loader or skills_data_loader

    def _get_product_discounts(self) -> Dict[str, Dict]:
        """获取产品折扣数据（懒加载）"""
        return self._data_loader.get_product_discounts()

    def _get_default_config(self) -> SkillConfig:
        return SkillConfig(
            name="negotiation",
            description="处理客户讨价还价、价格异议等谈判场景。当客户要求优惠、觉得价格高时激活。",
            skill_type=SkillType.NEGOTIATION,
            priority=15
        )

    def should_activate(self, context: Dict[str, Any]) -> bool:
        """判断是否应该激活"""
        query = context.get("query", "").lower()
        history = context.get("history", [])

        negotiation_keywords = [
            "便宜", "优惠", "打折", "降价", "太贵",
            "能不能", "少点", "便宜点", "再便宜", "能不能便宜",
            "少", "折扣", "减"
        ]

        # 统计历史中谈判次数
        negotiation_count = sum(
            1 for h in history
            if any(k in h.get("content", "").lower() for k in negotiation_keywords)
        )

        return any(keyword in query for keyword in negotiation_keywords) or negotiation_count >= 1

    def _extract_current_product(self, query: str, rag_results: list = None) -> Optional[Dict]:
        """
        从 query 或 RAG 结果中提取当前讨论的产品

        Args:
            query: 用户查询
            rag_results: RAG 检索结果

        Returns:
            产品折扣信息或 None
        """
        query_lower = query.lower()
        product_discounts = self._get_product_discounts()

        # 优先从 RAG 结果中提取产品
        if rag_results:
            for doc in rag_results:
                content = doc.get("content", "").lower()
                for key, product in product_discounts.items():
                    if key in content:
                        return {
                            "key": key,
                            **product
                        }

        # 从 query 中匹配产品关键词
        for key, product in product_discounts.items():
            name_lower = product["name"].lower()
            # 匹配产品名中的关键词
            if any(part in query_lower for part in key.split()):
                return {
                    "key": key,
                    **product
                }

        return None

    def _calculate_price(
        self,
        product: Dict,
        discount_level: int
    ) -> Dict[str, Any]:
        """
        计算指定折扣层级的价格

        Args:
            product: 产品信息
            discount_level: 折扣层级 (1-3)

        Returns:
            价格信息
        """
        list_price = product["list_price"]
        min_price = product["min_price"]

        if discount_level >= 3:
            # 最大优惠价
            final_price = min_price
            discount_description = "最大优惠价（底价）"
        else:
            discount_config = DISCOUNT_LEVELS[discount_level - 1]
            if discount_config["discount_rate"]:
                final_price = int(list_price * discount_config["discount_rate"])
                # 确保不超过最低价
                final_price = max(final_price, min_price)
            else:
                final_price = min_price
            discount_description = discount_config["description"]

        savings = list_price - final_price
        savings_percent = (savings / list_price) * 100 if list_price > 0 else 0

        return {
            "list_price": list_price,
            "final_price": final_price,
            "min_price": min_price,
            "savings": savings,
            "savings_percent": round(savings_percent, 1),
            "discount_description": discount_description,
            "discount_level": discount_level
        }

    def _get_negotiation_message(
        self,
        product: Dict,
        price_info: Dict,
        discount_level: int,
        customer_attitude: str = "normal"
    ) -> str:
        """
        生成谈判回复话术

        Args:
            product: 产品信息
            price_info: 价格计算结果
            discount_level: 当前折扣层级
            customer_attitude: 客户态度

        Returns:
            格式化回复
        """
        product_name = product["name"]
        final_price = price_info["final_price"]
        savings = price_info["savings"]

        messages = {
            1: f"好的，您诚心想要的话，我可以帮您申请活动优惠价。{product_name} 现在只要{final_price}元，比标价省了{savings}元！这已经是很好的优惠了。",

            2: f"我跟店长申请了一下，{product_name} 可以给您再优惠一点，到{final_price}元。这个价格真的很划算了，已经没什么空间了。",

            3: f"非常理解您的心情，但是{product_name} 的底价就是{price_info['min_price']}元了，这真的是公司能做到的最大优惠。再低就要亏本了。"
        }

        return messages.get(discount_level, messages[1])

    def _assess_customer_attitude(self, query: str, history: list) -> str:
        """
        评估客户态度

        Returns:
            态度类型: aggressive / normal / polite
        """
        query_lower = query.lower()

        # 激进态度关键词
        aggressive_keywords = ["不行", "太贵了", "投诉", "找领导", "别人家", "别人比你便宜"]
        polite_keywords = ["谢谢", "麻烦", "请问", "能不能", "好的"]

        if any(k in query_lower for k in aggressive_keywords):
            return "aggressive"
        elif any(k in query_lower for k in polite_keywords):
            return "polite"
        return "normal"

    def _determine_next_discount_level(
        self,
        current_level: int,
        customer_attitude: str,
        price_diff: int = 0
    ) -> int:
        """
        确定下一个折扣层级

        Args:
            current_level: 当前层级
            customer_attitude: 客户态度
            price_diff: 客户要求差价

        Returns:
            下一折扣层级
        """
        if current_level >= 3:
            return 3  # 已到底价

        # 难缠客户可以多让一点
        if customer_attitude == "aggressive" and current_level < 2:
            return current_level + 1

        # 价格差异大，谨慎让步
        if price_diff > 500 and current_level < 2:
            return current_level  # 先稳住

        # 正常谈判，逐步让步
        if current_level < 2:
            return current_level + 1

        return 3  # 给到底价

    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行价格谈判"""
        try:
            query = context.get("query", "")
            rag_results = context.get("rag_results", [])
            history = context.get("history", [])
            current_level = context.get("discount_level", 1)  # 谈判层级

            # 1. 提取当前产品
            product = self._extract_current_product(query, rag_results)

            # 2. 评估客户态度
            customer_attitude = self._assess_customer_attitude(query, history)

            # 3. 确定折扣层级
            next_level = self._determine_next_discount_level(
                current_level=current_level,
                customer_attitude=customer_attitude
            )

            if not product:
                return SkillResult(
                    success=False,
                    error="未识别到具体产品，无法提供价格优惠",
                    evaluation_score=0.0
                )

            # 4. 计算价格
            price_info = self._calculate_price(product, next_level)

            # 5. 生成话术
            message = self._get_negotiation_message(
                product=product,
                price_info=price_info,
                discount_level=next_level,
                customer_attitude=customer_attitude
            )

            # 6. 计算评估分数
            evaluation_score = self._calculate_evaluation_score(
                product=product,
                discount_level=next_level,
                price_info=price_info,
                customer_attitude=customer_attitude
            )

            response_data = {
                "intent": "negotiation",
                "product": {
                    "name": product["name"],
                    "list_price": product["list_price"],
                    "min_price": product["min_price"]
                },
                "discount_level": next_level,
                "price_info": price_info,
                "customer_attitude": customer_attitude,
                "can_negotiate": next_level < 3,
                "negotiation_message": message,
                "follow_up_needed": next_level < 3
            }

            logger.info(
                f"[Negotiation] 产品={product['name']}, "
                f"层级={next_level}, 最终价={price_info['final_price']}元"
            )

            return SkillResult(
                success=True,
                data=response_data,
                message=message,
                confidence=0.95,
                evaluation_score=evaluation_score
            )

        except Exception as e:
            logger.error(f"谈判Skill执行失败: {str(e)}")
            return SkillResult(
                success=False,
                error=str(e),
                evaluation_score=0.0
            )

    def _calculate_evaluation_score(
        self,
        product: Dict,
        discount_level: int,
        price_info: Dict,
        customer_attitude: str
    ) -> float:
        """
        计算谈判 Skill 输出质量评分

        评分维度：
        - 价格合理性（不能低于底价）
        - 客户态度适配度
        - 话术专业度
        """
        score = 0.6  # 基础分

        # 价格不低于底价
        if price_info["final_price"] >= price_info["min_price"]:
            score += 0.15

        # 折扣层级递进合理
        if 1 <= discount_level <= 3:
            score += 0.1

        # 话术适配态度
        if customer_attitude == "aggressive" and discount_level == 3:
            score += 0.1  # 难缠客户给到底价

        # 节省金额合理
        savings_percent = price_info.get("savings_percent", 0)
        if 5 <= savings_percent <= 25:
            score += 0.05

        return min(score, 1.0)

    def get_prompt(self) -> str:
        """获取谈判专用提示词"""
        return """你是一个经验丰富的销售谈判专家。要点：
1. 坚持价格底线，绝对不能让价低于成本价
2. 表现出真诚为客户争取优惠的态度
3. 逐步让步，让客户有成就感和参与感
4. 遇到难缠客户，保持冷静，态度坚定但不失礼貌
5. 可以适当强调产品价值，转移价格焦点
6. 遇到个人情绪激动的客户，可以申请上级协助"""
