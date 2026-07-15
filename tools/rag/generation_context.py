"""
RAG 三层架构 - Layer 3: 生成上下文层
负责上下文构建、源归属、知识库引用格式化
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class GenerationContext:
    """生成上下文"""
    context_text: str
    source_attributions: List[Dict[str, str]]
    metadata: Dict[str, Any]


class GenerationContextLayer:
    """
    Layer 3: 生成上下文层

    职责：
    1. 上下文构建 (根据意图构建结构化上下文)
    2. 源归属 (Source Attribution)
    3. 知识库引用格式化
    4. 无结果时的 fallback 消息
    """

    # 意图特定的上下文构建策略
    INTENT_CONTEXT_STRATEGY = {
        "price_inquiry": {
            "focus_fields": ["价格", "元", "¥", "折扣", "优惠"],
            "format": "price_list"
        },
        "product_spec": {
            "focus_fields": ["参数", "配置", "规格", "功能", "性能"],
            "format": "spec_list"
        },
        "comparison": {
            "focus_fields": [],
            "format": "comparison"
        },
        "troubleshooting": {
            "focus_fields": ["问题", "故障", "解决", "步骤"],
            "format": "steps"
        },
        "purchase": {
            "focus_fields": ["购买", "下单", "配送"],
            "format": "general"
        },
        "general": {
            "focus_fields": [],
            "format": "general"
        }
    }

    def build_context(
        self,
        documents: List[Dict[str, Any]],
        intent: str,
        query: str = ""
    ) -> GenerationContext:
        """
        根据意图构建结构化上下文

        Args:
            documents: 检索到的文档列表
            intent: 意图类型
            query: 原始查询

        Returns:
            GenerationContext 对象
        """
        if not documents:
            return GenerationContext(
                context_text=self.build_fallback_message(query),
                source_attributions=[],
                metadata={"intent": intent, "doc_count": 0}
            )

        strategy = self.INTENT_CONTEXT_STRATEGY.get(intent, self.INTENT_CONTEXT_STRATEGY["general"])
        format_type = strategy["format"]

        if format_type == "price_list":
            context_text = self._build_price_context(documents)
        elif format_type == "spec_list":
            context_text = self._build_spec_context(documents)
        elif format_type == "comparison":
            context_text = self._build_comparison_context(documents)
        elif format_type == "steps":
            context_text = self._build_steps_context(documents)
        else:
            context_text = self._build_general_context(documents)

        # 构建源归属
        attributions = self.format_with_sources(documents)

        return GenerationContext(
            context_text=context_text,
            source_attributions=attributions,
            metadata={
                "intent": intent,
                "doc_count": len(documents),
                "format": format_type
            }
        )

    def _build_price_context(self, documents: List[Dict[str, Any]]) -> str:
        """构建价格相关的上下文"""
        context_parts = ["【价格信息】\n"]

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            # 提取价格相关信息
            if any(kw in content for kw in ["价格", "元", "¥", "折扣"]):
                context_parts.append(f"{i}. {content}")

        return "\n".join(context_parts) if len(context_parts) > 1 else self._build_general_context(documents)

    def _build_spec_context(self, documents: List[Dict[str, Any]]) -> str:
        """构建规格参数相关的上下文"""
        context_parts = ["【产品参数】\n"]

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            context_parts.append(f"{i}. {content}")

        return "\n".join(context_parts)

    def _build_comparison_context(self, documents: List[Dict[str, Any]]) -> str:
        """构建对比相关的上下文"""
        context_parts = ["【对比信息】\n"]

        for i, doc in enumerate(documents, 1):
            source = doc.get("source_file", "未知")
            content = doc.get("content", "")
            context_parts.append(f"{i}. [{source}]\n   {content}")

        return "\n".join(context_parts)

    def _build_steps_context(self, documents: List[Dict[str, Any]]) -> str:
        """构建故障排查步骤相关的上下文"""
        context_parts = ["【故障排查步骤】\n"]

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            context_parts.append(f"{i}. {content}")

        return "\n".join(context_parts)

    def _build_general_context(self, documents: List[Dict[str, Any]]) -> str:
        """构建通用上下文"""
        context_parts = [f"【检索到 {len(documents)} 条相关信息】\n"]

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            context_parts.append(f"{i}. {content}")

        return "\n".join(context_parts)

    def format_with_sources(self, documents: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        格式化源归属信息

        Args:
            documents: 文档列表

        Returns:
            源归属列表
        """
        attributions = []
        seen_sources = set()

        for doc in documents:
            source = doc.get("source_file", "未知")
            chunk_id = doc.get("chunk_id", "")

            if source not in seen_sources:
                seen_sources.add(source)
                attributions.append({
                    "source": source,
                    "chunk_id": chunk_id,
                    "type": self._get_source_type(source)
                })

        return attributions

    def _get_source_type(self, source: str) -> str:
        """根据文件名判断源类型"""
        source_lower = source.lower()
        if "faq" in source_lower or "q&a" in source_lower:
            return "FAQ"
        elif "价格" in source or "price" in source_lower:
            return "价格表"
        elif "手册" in source or "manual" in source_lower:
            return "用户手册"
        elif "指南" in source or "guide" in source_lower:
            return "使用指南"
        return "知识库"

    def build_fallback_message(self, query: str) -> str:
        """
        构建无结果时的 fallback 消息

        Args:
            query: 原始查询

        Returns:
            fallback 消息
        """
        return f"抱歉，我在知识库中没有找到与「{query}」直接相关的信息。\n\n建议您：\n1. 尝试使用不同的关键词\n2. 咨询人工客服获取更详细的帮助\n3. 查看常见问题FAQ获取更多帮助"

    def format_for_llm(self, context: GenerationContext, include_sources: bool = True) -> str:
        """
        格式化上下文用于 LLM 生成

        Args:
            context: GenerationContext 对象
            include_sources: 是否包含源归属

        Returns:
            格式化后的字符串
        """
        parts = [context.context_text, "\n"]

        if include_sources and context.source_attributions:
            parts.append("\n【参考来源】")
            for attr in context.source_attributions:
                parts.append(f"- {attr['source']} ({attr['type']})")

        return "".join(parts)


# 全局单例
generation_context_layer = GenerationContextLayer()