"""
增强版生成上下文层 - 集成上下文工程

整合三层记忆架构与现有 RAG 系统

Manus 技巧：
- 通过复述操控注意力
- 保留错误内容让模型学习
- 多样性增强避免少样本陷阱

Claude Code 技巧：
- 动态上下文注入
- 意图演进跟踪
- 92% 阈值触发压缩
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from tools.rag.context_engineering import (
    ContextEngineeringManager,
    context_engineering_manager,
    MemoryTier,
    CompressedMemory,
    ConversationTurn
)
from tools.rag.query_understanding import query_understanding_layer, QueryUnderstandingResult

from core.logger import LoggerManager

logger = LoggerManager.get_logger("enhanced_context")


@dataclass
class GenerationContext:
    """生成上下文（增强版）"""
    context_blocks: List[Dict[str, Any]] = field(default_factory=list)
    source_attributions: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    intent: str = "general"
    context_engine_info: Dict[str, Any] = field(default_factory=dict)


class EnhancedGenerationContextLayer:
    """
    增强版生成上下文层

    功能：
    1. 整合三层记忆架构
    2. 支持意图演进跟踪
    3. 动态上下文注入
    4. 上下文连续性维护

    相对于原版的改进：
    - 从单轮格式化工具升级为多轮上下文管理器
    - 集成上下文工程最佳实践
    """

    INTENT_CONTEXT_STRATEGY = {
        "price_inquiry": {
            "focus_fields": ["价格", "元", "¥", "折扣", "优惠"],
            "format": "price_list",
            "importance": 1.0
        },
        "product_spec": {
            "focus_fields": ["参数", "配置", "规格", "功能", "性能"],
            "format": "spec_list",
            "importance": 1.0
        },
        "comparison": {
            "focus_fields": ["对比", "比较", "区别", "差异"],
            "format": "comparison",
            "importance": 1.0
        },
        "troubleshooting": {
            "focus_fields": ["问题", "故障", "解决", "售后"],
            "format": "steps",
            "importance": 1.0
        },
        "purchase": {
            "focus_fields": ["购买", "下单", "订购"],
            "format": "general",
            "importance": 0.9
        },
        "general": {
            "focus_fields": [],
            "format": "general",
            "importance": 0.7
        }
    }

    def __init__(self):
        self.context_engine = context_engineering_manager
        logger.info("[EnhancedGenerationContext] 初始化完成")

    def build_context(
        self,
        documents: List[Dict],
        intent: str,
        query: str = "",
        user_id: str = None,
        chat_history: List[Dict] = None
    ) -> GenerationContext:
        """
        构建生成上下文（增强版）

        Args:
            documents: RAG 检索结果
            intent: 当前意图
            query: 当前查询
            user_id: 用户 ID（用于长期记忆）
            chat_history: 对话历史

        Returns:
            GenerationContext 对象
        """
        logger.debug(f"[EnhancedGenerationContext] 构建上下文: intent={intent}, query={query}")

        context_blocks = []
        source_attributions = []

        strategy = self.INTENT_CONTEXT_STRATEGY.get(
            intent,
            self.INTENT_CONTEXT_STRATEGY["general"]
        )

        context_blocks.append({
            "type": "intent_strategy",
            "format": strategy["format"],
            "focus_fields": strategy["focus_fields"],
            "intent": intent
        })

        if documents:
            context_blocks.extend(self._build_document_blocks(documents, strategy))
            source_attributions = self._build_source_attributions(documents)

        unified_context = self.context_engine.get_unified_context(
            user_id=user_id,
            include_long_term=True
        )

        if unified_context["stats"]["short_term_turns"] > 0:
            context_blocks.append({
                "type": "conversation_history",
                "turns": unified_context["short_term"],
                "density": unified_context["stats"]["density"]
            })

        if unified_context["medium_term"]:
            context_blocks.append({
                "type": "compressed_history",
                "memories": unified_context["medium_term"]
            })

        if unified_context["long_term"]:
            context_blocks.append({
                "type": "user_background",
                "content": unified_context["long_term"]
            })

        if unified_context["intent_continuity"]:
            context_blocks.append({
                "type": "intent_continuity",
                "content": unified_context["intent_continuity"]
            })

        generation_context = GenerationContext(
            context_blocks=context_blocks,
            source_attributions=source_attributions,
            metadata={
                "intent": intent,
                "doc_count": len(documents),
                "query": query,
                "user_id": user_id
            },
            intent=intent,
            context_engine_info=unified_context["stats"]
        )

        return generation_context

    def _build_document_blocks(
        self,
        documents: List[Dict],
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构建文档块"""
        blocks = []
        focus_fields = strategy.get("focus_fields", [])

        for i, doc in enumerate(documents[:5]):
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})

            cited_snippet = self._extract_cited_snippet(content, focus_fields)

            blocks.append({
                "type": "document",
                "index": i + 1,
                "content": content,
                "cited_snippet": cited_snippet,
                "source": metadata.get("source_file", "未知来源"),
                "score": doc.get("score", 0.0)
            })

        return blocks

    def _extract_cited_snippet(
        self,
        content: str,
        focus_fields: List[str],
        max_length: int = 200
    ) -> str:
        """提取引用片段"""
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if any(field in line for field in focus_fields):
                return line[:max_length] + ("..." if len(line) > max_length else "")

        for line in lines[:3]:
            if line.strip() and len(line.strip()) > 20:
                return line.strip()[:max_length] + ("..." if len(line.strip()) > max_length else "")

        return content[:max_length] + "..." if len(content) > max_length else content

    def _build_source_attributions(self, documents: List[Dict]) -> List[Any]:
        """构建源归属"""
        attributions = []

        for doc in documents[:3]:
            attributions.append({
                "source_id": doc.get("id", ""),
                "source_name": doc.get("metadata", {}).get("source_file", "未知来源"),
                "relevance_score": doc.get("score", 0.0)
            })

        return attributions

    def format_for_llm(
        self,
        generation_context: GenerationContext,
        include_continuity: bool = True
    ) -> str:
        """
        格式化为 LLM 可用的提示词

        Manus 技巧：
        - 将目标复述到上下文末尾
        - 多样性增强避免模式复制
        """
        parts = []

        for block in generation_context.context_blocks:
            block_type = block.get("type")

            if block_type == "intent_strategy":
                parts.append(f"[查询策略] 意图: {block['intent']}, 格式: {block['format']}")

            elif block_type == "document":
                snippet = block.get("cited_snippet", "")
                source = block.get("source", "")
                parts.append(f"[文档{block['index']}] ({source})\n{snippet}")

            elif block_type == "conversation_history":
                turns = block.get("turns", [])
                if turns:
                    turn_texts = [f"{t.role}: {t.content[:100]}" for t in turns[-5:]]
                    parts.append("[对话历史]\n" + "\n".join(turn_texts))

            elif block_type == "compressed_history":
                memories = block.get("memories", [])
                if memories:
                    summaries = [m.summary for m in memories[-3:]]
                    parts.append("[历史摘要]\n" + "\n".join(f"- {s}" for s in summaries))

            elif block_type == "user_background":
                content = block.get("content", "")
                if content:
                    parts.append(f"[用户背景]\n{content}")

            elif block_type == "intent_continuity":
                if include_continuity:
                    content = block.get("content", "")
                    if content:
                        parts.append(f"[上下文连续性]\n{content}")

        return "\n\n".join(parts)

    def track_turn(
        self,
        role: str,
        content: str,
        intent: str,
        entities: List[str] = None,
        rag_results: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ):
        """跟踪对话轮次到上下文工程"""
        self.context_engine.add_turn(
            role=role,
            content=content,
            intent=intent,
            entities=entities,
            rag_results=rag_results,
            metadata=metadata
        )

    def update_user_preference(
        self,
        user_id: str,
        key: str,
        value: Any
    ):
        """更新用户偏好"""
        self.context_engine.long_term.update_preference(user_id, key, value)

    def add_user_entity(
        self,
        user_id: str,
        entity: str,
        topic: str
    ):
        """添加用户讨论实体"""
        self.context_engine.long_term.add_entity(user_id, entity, topic)

    def save_memory(self, user_id: str) -> bool:
        """保存长期记忆"""
        return self.context_engine.save_long_term_memory(user_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.context_engine.get_stats()


enhanced_generation_context_layer = EnhancedGenerationContextLayer()
