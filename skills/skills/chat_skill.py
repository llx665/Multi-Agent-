"""
聊天Skill
作为客服助手的闲聊技能，当用户进行日常交流、问候或无明确购买意向时激活

特点：
- 语气和善、态度友好
- 最低优先级（仅在其他意图都不匹配时激活）
- 处理寒暄、问候、日常对话等场景
"""

import re
import random
from typing import Any, Dict, List, Optional
from loguru import logger

from ..base import BaseSkill, SkillConfig, SkillResult, SkillType


class ChatSkill(BaseSkill):
    """聊天Skill - 客服助手闲聊"""

    # 问候语匹配
    GREETING_PATTERNS = [
        r"你好", r"您好", r"hi|hello|hey", r"早上好", r"下午好", r"晚上好",
        r"在吗", r"在不在", r"有人吗", r"你好呀", r"嗨", r"哈喽"
    ]

    # 感谢语匹配
    THANKS_PATTERNS = [
        r"谢谢", r"感谢", r"多谢", r"谢啦", r"谢了", r"thx", r"thanks"
    ]

    # 告别语匹配
    GOODBYE_PATTERNS = [
        r"再见", r"拜拜", r" bye", r"下次见", r"走了", r"溜了", r"退下"
    ]

    # 称赞语匹配
    COMPLIMENT_PATTERNS = [
        r"不错", r"厉害", r"棒", r"优秀", r"好评", r"满意", r"好用"
    ]

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)
        self._greeting_templates = [
            "您好呀！有什么可以帮您的吗？😊",
            "Hello！很高兴为您服务，请问有什么问题想咨询呢？",
            "您好！我是您的智能客服助手，有什么需要随时问我哦～",
            "嗨！欢迎来到客服中心，请问有什么可以帮到您？",
            "您好呀！无论是产品咨询、使用问题还是其他疑问，我都很乐意帮忙～"
        ]
        self._small_talk_responses = {
            "weather": [
                "今天天气不错呢，希望您也有好心情！🌤️",
                "天气影响着心情，希望今天是美好的一天！",
            ],
            "time": [
                "感谢您的耐心！希望我的回答对您有帮助～",
                "希望我的回复能帮到您！如果还有其他问题随时问我哦！",
            ],
            "default": [
                "明白了！有什么需要帮忙的尽管说～",
                "好的呀！我在这里，随时为您提供帮助！",
                "了解！请问还有什么想了解的吗？",
            ]
        }

    def _get_default_config(self) -> SkillConfig:
        return SkillConfig(
            name="chat",
            description="处理闲聊、寒暄、日常交流等场景。当用户没有明确购买意向或进行日常对话时激活。",
            skill_type=SkillType.GENERAL,
            priority=1  # 最低优先级，仅作为兜底
        )

    def should_activate(self, context: Dict[str, Any]) -> bool:
        """
        判断是否应该激活

        注意：这个Skill设计为最低优先级，所以几乎所有查询都可以激活。
        但在其他Skill（如销售、技术支持）被激活后，这个Skill不会被选用，
        因为执行器会选择优先级最高的Skill。
        """
        query = context.get("query", "").lower()

        # 如果是纯文本对话，几乎都可以激活
        # 但如果有明确的商业意图关键词，会被其他Skill截断
        return True

    def _classify_intent(self, query: str) -> str:
        """分类闲聊意图"""
        query_lower = query.lower()

        # 检查各种意图
        for pattern in self.GREETING_PATTERNS:
            if re.search(pattern, query_lower):
                return "greeting"

        for pattern in self.THANKS_PATTERNS:
            if re.search(pattern, query_lower):
                return "thanks"

        for pattern in self.GOODBYE_PATTERNS:
            if re.search(pattern, query_lower):
                return "goodbye"

        for pattern in self.COMPLIMENT_PATTERNS:
            if re.search(pattern, query_lower):
                return "compliment"

        return "casual"

    def _generate_greeting_response(self) -> str:
        """生成问候回复"""
        return random.choice(self._greeting_templates)

    def _generate_thanks_response(self) -> str:
        """生成感谢回复"""
        thanks_templates = [
            "不客气！很高兴能帮到您～有什么其他问题随时来找我哦！",
            "不用谢！这是我的职责所在，祝您生活愉快！😊",
            "客气啦！希望我的回答对您有帮助，期待下次为您服务～",
            "不客气呀！如果有任何疑问，随时问我！祝您购物愉快！"
        ]
        return random.choice(thanks_templates)

    def _generate_goodbye_response(self) -> str:
        """生成告别回复"""
        goodbye_templates = [
            "再见啦！期待下次为您服务，祝您生活愉快！👋",
            "拜拜～有任何问题随时来找我哦，祝您一切顺利！",
            "再见呀！感谢您的咨询，希望您有美好的一天！😊",
            "好的，下次见！祝您购物愉快，一切顺利！🌟"
        ]
        return random.choice(goodbye_templates)

    def _generate_compliment_response(self) -> str:
        """生成称赞回复"""
        compliment_templates = [
            "谢谢您的认可！您的满意是我最大的动力～会继续努力的！😊",
            "感谢您的夸奖！能帮到您我也非常开心！",
            "太好了！您的肯定让我更有动力为您提供更好的服务～"
        ]
        return random.choice(compliment_templates)

    def _generate_casual_response(self, query: str) -> str:
        """生成日常对话回复"""
        casual_templates = [
            "明白了！请问您想了解哪方面的信息呢？产品咨询、技术支持我都可以帮忙～",
            "好的呀！我是您的智能客服助手，可以帮您解答产品问题、查询价格、了解优惠等，随时问我哦！",
            "了解！虽然我暂时不太确定您想了解什么，但产品相关的问题都可以问我呢～",
            "我在这里为您服务！无论是售前咨询、使用问题还是售后帮助，都可以随时告诉我～"
        ]
        return random.choice(casual_templates)

    def _generate_response(self, query: str) -> str:
        """根据意图生成回复"""
        intent = self._classify_intent(query)

        response_map = {
            "greeting": self._generate_greeting_response,
            "thanks": self._generate_thanks_response,
            "goodbye": self._generate_goodbye_response,
            "compliment": self._generate_compliment_response,
            "casual": self._generate_casual_response
        }

        generator = response_map.get(intent, response_map["casual"])
        return generator() if callable(generator) else generator

    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行聊天Skill

        生成友好的客服回复，处理日常对话场景
        """
        try:
            query = context.get("query", "")

            # 分类意图
            intent = self._classify_intent(query)
            logger.info(f"[ChatSkill] 意图分类: {intent}")

            # 生成回复
            response_text = self._generate_response(query)

            # 评估分数（闲聊Skill评分相对较低，因为不解决实际问题）
            evaluation_score = 0.6

            response_data = {
                "intent": "chat",
                "chat_intent": intent,
                "response": response_text,
                "follow_up_needed": True
            }

            logger.info(f"[ChatSkill] 生成聊天回复: {response_text[:50]}...")

            return SkillResult(
                success=True,
                data=response_data,
                message="聊天回复已生成",
                confidence=0.7,
                evaluation_score=evaluation_score
            )

        except Exception as e:
            logger.error(f"聊天Skill执行失败: {str(e)}")
            return SkillResult(
                success=False,
                error=str(e),
                evaluation_score=0.0
            )

    def get_prompt(self) -> str:
        """获取聊天Skill专用提示词"""
        return """你是一个热情友好的智能客服助手。要点：
1. 语气亲切和善，像朋友聊天一样自然
2. 适当使用表情符号增加亲和力
3. 主动引导用户提出问题或需求
4. 如果用户只是寒暄，先回应寒暄，再引导到正题
5. 保持积极乐观的态度，传递正能量
6. 遇到无法回答的问题，礼貌说明并引导用户提供更多信息"""
