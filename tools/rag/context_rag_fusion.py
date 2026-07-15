"""
Context+RAG融合层 - 实现上下文与RAG的双向信息流
打通 Context Engineering 和 RAG System，让检索更智能、生成更准确

核心设计：
1. Context-to-RAG: 利用上下文元数据和Skill上下文优化检索策略
2. RAG-to-Context: 将RAG结果智能注入到三层记忆中
3. 自适应融合: 根据检索质量动态调整生成策略
"""

import json
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading

from core.logger import LoggerManager
from core.session_context import SessionContext
from tools.rag.intent_classifier import (
    UnifiedIntentClassifier,
    IntentClassificationResult
)

logger = LoggerManager.get_logger("context_rag_fusion")


class RetrievalQuality(Enum):
    """检索质量等级"""
    HIGH = "high"        # 检索到高质量文档
    MEDIUM = "medium"    # 检索结果一般
    LOW = "low"          # 检索结果质量低
    NONE = "none"        # 未检索到文档


class FusionStrategy(Enum):
    """融合策略"""
    RAG_PRIMARY = "rag_primary"      # RAG结果为主
    CONTEXT_PRIMARY = "context_primary"  # 上下文为主
    HYBRID = "hybrid"               # 混合策略
    CONTEXT_ONLY = "context_only"    # 仅使用上下文


@dataclass
class ContextAwareQuery:
    """上下文感知的查询"""
    original_query: str
    enhanced_query: str
    query_context: Dict[str, Any]
    entities: List[str]
    intent: str
    metadata_hints: Dict[str, Any]
    skill_context_applied: bool


@dataclass
class FusionContext:
    """融合上下文"""
    short_term_context: str
    medium_term_context: str
    long_term_context: str
    rag_context: str
    skill_context: Dict[str, Any]
    metadata_context: Dict[str, Any]
    quality: RetrievalQuality
    fusion_strategy: FusionStrategy
    confidence: float
    sources: List[str]


@dataclass
class FusionResult:
    """融合结果"""
    response: str
    quality: RetrievalQuality
    fusion_strategy: FusionStrategy
    confidence: float
    used_sources: List[str]
    context_summary: str
    metadata: Dict[str, Any]



class ContextExtractor:
    """
    上下文提取器 - 从SessionContext中提取关键信息用于RAG优化

    功能：
    1. 提取元数据（客户类型、产品偏好、折扣层级）
    2. 提取Skill上下文（业务上下文）
    3. 提取对话历史关键信息
    4. 生成检索提示
    """

    def __init__(self):
        self._lock = threading.RLock()
        logger.info("[ContextExtractor] 初始化完成")

    def extract_for_rag(
        self,
        context: SessionContext,
        current_query: str
    ) -> ContextAwareQuery:
        """
        从SessionContext中提取用于优化RAG检索的信息

        Args:
            context: 会话上下文
            current_query: 当前查询

        Returns:
            ContextAwareQuery: 包含检索优化信息的查询对象
        """
        with self._lock:
            metadata = context.metadata
            skill_context = context.skill_context
            recent_history = [
                {"role": t.role, "content": t.content}
                for t in context.turn_history[-6:]
            ]

            enhanced_parts = [current_query]

            entities = []
            metadata_hints = {}
            intent = "general"

            if metadata.get("current_product"):
                product = metadata["current_product"]
                enhanced_parts.append(product)
                entities.append(product)
                metadata_hints["current_product"] = product

            if metadata.get("customer_type"):
                customer_type = metadata["customer_type"]
                metadata_hints["customer_type"] = customer_type
                logger.debug(f"[ContextExtractor] 客户类型: {customer_type}")

            if metadata.get("preference"):
                preference = metadata["preference"]
                enhanced_parts.append(str(preference))
                metadata_hints["preference"] = preference

            discount_level = metadata.get("discount_level", 1)
            if discount_level > 1:
                metadata_hints["discount_level"] = discount_level

            skill_entities = self._extract_skill_entities(skill_context)
            entities.extend(skill_entities)
            enhanced_parts.extend(skill_entities[:3])

            for turn in reversed(recent_history):
                if turn["role"] == "user":
                    content = turn["content"]
                    if any(kw in content for kw in ["买", "价格", "优惠", "产品"]):
                        intent = "sales"
                        break
                    elif any(kw in content for kw in ["坏", "问题", "故障", "怎么"]):
                        intent = "tech_support"
                        break
                    elif any(kw in content for kw in ["便宜", "打折", "便宜点"]):
                        intent = "negotiation"
                        break

            enhanced_query = " ".join(enhanced_parts)
            query_context = {
                "recent_history": recent_history,
                "metadata": metadata,
                "skill_context_keys": list(skill_context.keys()),
                "total_turns": len(context.turn_history)
            }

            return ContextAwareQuery(
                original_query=current_query,
                enhanced_query=enhanced_query,
                query_context=query_context,
                entities=list(set(entities)),
                intent=intent,
                metadata_hints=metadata_hints,
                skill_context_applied=len(skill_entities) > 0
            )

    def _extract_skill_entities(self, skill_context: Dict[str, Any]) -> List[str]:
        """从Skill上下文中提取实体"""
        entities = []

        for skill_name, skill_data in skill_context.items():
            if not isinstance(skill_data, dict):
                continue

            data = skill_data.get("data", {})

            if skill_name == "customer_classifier":
                customer_type = data.get("customer_type", "")
                if customer_type:
                    entities.append(f"客户类型:{customer_type}")

            elif skill_name == "sales_agent":
                product = data.get("product", {})
                if isinstance(product, dict) and product.get("name"):
                    entities.append(product["name"])

            elif skill_name == "negotiation":
                product_data = data.get("product", {})
                if isinstance(product_data, dict) and product_data.get("name"):
                    entities.append(product_data["name"])
                discount_info = data.get("discount_info", {})
                if discount_info:
                    entities.append(f"折扣:{discount_info.get('current_discount', '未知')}")

        return entities

    def generate_metadata_hint(self, metadata: Dict[str, Any]) -> str:
        """
        根据元数据生成检索提示

        Args:
            metadata: 会话元数据

        Returns:
            格式化的提示字符串
        """
        hints = []

        if metadata.get("customer_type"):
            customer_type = metadata["customer_type"]
            type_hints = {
                "price_sensitive": "注意：此客户对价格敏感，适合推荐性价比高的产品",
                "rational": "注意：此客户是理性消费者，需要详细的产品参数对比",
                "difficult": "注意：此客户较难处理，需要耐心解答",
                "hesitant": "注意：此客户犹豫不决，需要给出明确的购买建议",
                "urgent": "注意：此客户有紧急需求，需要快速响应"
            }
            hint = type_hints.get(customer_type, f"客户类型: {customer_type}")
            hints.append(hint)

        if metadata.get("current_product"):
            hints.append(f"当前产品: {metadata['current_product']}")

        if metadata.get("discount_level", 1) > 1:
            hints.append(f"当前折扣层级: {metadata['discount_level']}")

        return " | ".join(hints) if hints else ""


class RAGResultInjector:
    """
    RAG结果注入器 - 将检索结果智能注入到三层记忆中

    功能：
    1. 评估检索结果质量
    2. 提取关键信息到metadata
    3. 更新skill_context
    4. 触发中期记忆压缩（如果需要）
    """

    def __init__(self, context_manager=None):
        self._lock = threading.RLock()
        self.context_manager = context_manager
        self._quality_thresholds = {
            "high": 0.7,
            "medium": 0.2,
            "low": 0.05
        }
        logger.info("[RAGResultInjector] 初始化完成")

    def _extract_quality_terms(self, text: str) -> List[str]:
        """Extract stable product/query terms from Chinese and mixed text."""
        if not text:
            return []

        lower = text.lower()
        terms = []

        known_terms = [
            "投影仪", "投影机", "智能投影仪", "手机", "智能手机", "耳机",
            "价格", "多少钱", "报价", "便宜", "优惠", "配置", "分辨率",
            "屏幕", "续航", "x12", "x12pro"
        ]
        for term in known_terms:
            if term in lower:
                terms.append(term)

        model_matches = re.findall(
            r"[a-zA-Z]?\d+(?:\s*(?:pro|max|plus|air|mini|se|ultra))?",
            lower,
            re.IGNORECASE,
        )
        terms.extend(match.replace(" ", "") for match in model_matches if match.strip())

        terms.extend(re.findall(r"\d+(?:gb|mah|元|k|p)?", lower, re.IGNORECASE))

        seen = set()
        deduped = []
        for term in terms:
            normalized = term.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return deduped

    def evaluate_retrieval_quality(
        self,
        documents: List[Dict[str, Any]],
        query: str
    ) -> Tuple[RetrievalQuality, float]:
        """
        评估检索结果质量

        Args:
            documents: 检索到的文档列表
            query: 查询文本

        Returns:
            (检索质量等级, 置信度分数)
        """
        if not documents:
            return RetrievalQuality.NONE, 0.0

        query_terms = self._extract_quality_terms(query)

        total_relevance = 0.0
        documents_with_keyword = 0

        for doc in documents:
            content = doc.get("content", "").lower()
            similarity_score = doc.get("similarity_score", 0.0)

            matched_terms = [term for term in query_terms if term in content]

            if query_terms:
                keyword_ratio = len(matched_terms) / len(query_terms)
            else:
                keyword_ratio = 0

            relevance = (keyword_ratio * 0.3 + similarity_score * 0.7)
            total_relevance += relevance

            if keyword_ratio > 0.1:
                documents_with_keyword += 1

        avg_relevance = total_relevance / len(documents)
        coverage = documents_with_keyword / len(documents)

        confidence = (avg_relevance * 0.6 + coverage * 0.4)

        if confidence >= self._quality_thresholds["high"]:
            quality = RetrievalQuality.HIGH
        elif confidence >= self._quality_thresholds["medium"]:
            quality = RetrievalQuality.MEDIUM
        elif confidence >= self._quality_thresholds["low"]:
            quality = RetrievalQuality.LOW
        else:
            quality = RetrievalQuality.NONE

        logger.info(f"[RAGResultInjector] 检索质量评估: quality={quality.value}, confidence={confidence:.3f}")
        return quality, confidence

    def inject_into_context(
        self,
        context: SessionContext,
        documents: List[Dict[str, Any]],
        query: str,
        quality: RetrievalQuality,
        confidence: float
    ) -> Dict[str, Any]:
        """
        将RAG结果注入到SessionContext

        Args:
            context: 会话上下文
            documents: 检索到的文档
            query: 查询文本
            quality: 检索质量
            confidence: 置信度

        Returns:
            注入摘要
        """
        with self._lock:
            injection_summary = {
                "query": query,
                "quality": quality.value,
                "confidence": confidence,
                "doc_count": len(documents),
                "entities_extracted": [],
                "metadata_updated": []
            }

            if quality == RetrievalQuality.NONE or not documents:
                logger.debug("[RAGResultInjector] 未检索到文档，跳过注入")
                return injection_summary

            context.update_rag_cache(query, documents)
            injection_summary["metadata_updated"].append("rag_cache")

            entities = self._extract_key_entities(documents)
            injection_summary["entities_extracted"] = entities

            if quality in [RetrievalQuality.HIGH, RetrievalQuality.MEDIUM]:
                self._update_metadata_from_rag(context, documents, entities)
                injection_summary["metadata_updated"].append("metadata")

            self._update_skill_context_from_rag(context, documents, query)
            injection_summary["metadata_updated"].append("skill_context")

            logger.info(f"[RAGResultInjector] 注入完成: {injection_summary}")
            return injection_summary

    def _extract_key_entities(self, documents: List[Dict[str, Any]]) -> List[str]:
        """从文档中提取关键实体"""
        entities = []

        for doc in documents:
            content = doc.get("content", "")

            import re
            model_pattern = r'([a-zA-Z]?\d+(?:\s*(?:Pro|Max|Plus|Air|Mini|SE|Ultra))?)'
            models = re.findall(model_pattern, content, re.IGNORECASE)
            entities.extend([m.strip().lower() for m in models if m.strip()])

            product_names = re.findall(r'产品名称[：:]\s*([^\n，,。]+)', content)
            entities.extend(product_names[:2])

            price_pattern = r'[\d,]+元|¥[\d.]+|价格[：:]\s*([\d,]+)'
            prices = re.findall(price_pattern, content)
            if prices:
                entities.append(f"价格:{prices[0]}")

        seen = set()
        unique_entities = []
        for e in entities:
            if e not in seen:
                seen.add(e)
                unique_entities.append(e)

        return unique_entities[:10]

    def _update_metadata_from_rag(
        self,
        context: SessionContext,
        documents: List[Dict[str, Any]],
        entities: List[str]
    ):
        """从RAG结果更新metadata"""
        if not entities:
            return

        if not context.metadata.get("discussed_products"):
            context.metadata["discussed_products"] = []

        for entity in entities[:5]:
            if entity and ":" not in entity:
                if entity not in context.metadata["discussed_products"]:
                    context.metadata["discussed_products"].append(entity)

        context.metadata["last_rag_quality"] = {
            "quality": "high" if len(documents) > 0 else "low",
            "timestamp": datetime.now().isoformat()
        }

    def _update_skill_context_from_rag(
        self,
        context: SessionContext,
        documents: List[Dict[str, Any]],
        query: str
    ):
        """从RAG结果更新skill_context"""
        rag_summary = {
            "documents": [
                {
                    "content": doc.get("content", "")[:200],
                    "source": doc.get("source_file", "未知")
                }
                for doc in documents[:3]
            ],
            "total_count": len(documents),
            "query": query,
            "timestamp": datetime.now().isoformat()
        }

        context.update_skill_context("rag_summary", rag_summary)


class AdaptiveFusionEngine:
    """
    自适应融合引擎 - 根据检索质量和上下文状态选择最佳融合策略

    融合策略选择逻辑：
    - HIGH quality + good context → HYBRID
    - HIGH quality + weak context → RAG_PRIMARY
    - MEDIUM quality → HYBRID
    - LOW quality → CONTEXT_PRIMARY
    - NONE quality → CONTEXT_ONLY
    """

    def __init__(self):
        self._lock = threading.RLock()
        logger.info("[AdaptiveFusionEngine] 初始化完成")

    def select_strategy(
        self,
        retrieval_quality: RetrievalQuality,
        context_strength: float,
        intent: str
    ) -> Tuple[FusionStrategy, float]:
        """
        选择融合策略

        Args:
            retrieval_quality: 检索质量
            context_strength: 上下文强度 (0-1)
            intent: 意图类型

        Returns:
            (融合策略, 置信度)
        """
        with self._lock:
            if retrieval_quality == RetrievalQuality.HIGH:
                if context_strength > 0.6:
                    strategy = FusionStrategy.HYBRID
                    confidence = 0.85
                else:
                    strategy = FusionStrategy.RAG_PRIMARY
                    confidence = 0.75

            elif retrieval_quality == RetrievalQuality.MEDIUM:
                if context_strength > 0.5:
                    strategy = FusionStrategy.HYBRID
                    confidence = 0.70
                else:
                    strategy = FusionStrategy.CONTEXT_PRIMARY
                    confidence = 0.65

            elif retrieval_quality == RetrievalQuality.LOW:
                strategy = FusionStrategy.CONTEXT_PRIMARY
                confidence = 0.60

            else:
                strategy = FusionStrategy.CONTEXT_ONLY
                confidence = 0.50

            if intent in ["greeting", "farewell"]:
                strategy = FusionStrategy.CONTEXT_ONLY
                confidence = 0.90

            logger.info(f"[AdaptiveFusionEngine] 策略选择: {strategy.value}, confidence={confidence:.2f}")
            return strategy, confidence

    def build_fusion_context(
        self,
        short_term: str,
        medium_term: str,
        long_term: str,
        rag_context: str,
        skill_context: Dict[str, Any],
        metadata: Dict[str, Any],
        strategy: FusionStrategy,
        quality: RetrievalQuality
    ) -> FusionContext:
        """
        构建融合上下文

        Args:
            short_term: 短期上下文
            medium_term: 中期上下文
            long_term: 长期上下文
            rag_context: RAG上下文
            skill_context: Skill上下文
            metadata: 元数据
            strategy: 融合策略
            quality: 检索质量

        Returns:
            FusionContext
        """
        priority_components = []

        if strategy == FusionStrategy.RAG_PRIMARY:
            priority_components = ["rag", "short", "medium", "long", "skill"]
        elif strategy == FusionStrategy.CONTEXT_PRIMARY:
            priority_components = ["short", "skill", "rag", "medium", "long"]
        elif strategy == FusionStrategy.HYBRID:
            priority_components = ["rag", "short", "skill", "medium", "long"]
        else:
            priority_components = ["short", "skill", "medium", "long"]

        component_map = {
            "rag": rag_context,
            "short": short_term,
            "medium": medium_term,
            "long": long_term,
            "skill": self._format_skill_context(skill_context)
        }

        ordered_contexts = []
        for key in priority_components:
            if component_map.get(key):
                ordered_contexts.append(component_map[key])

        combined_context = "\n---\n".join(ordered_contexts)

        sources = []
        if rag_context:
            sources.append("knowledge_base")
        if skill_context:
            sources.append("skill_context")
        if long_term:
            sources.append("long_term_memory")

        return FusionContext(
            short_term_context=short_term,
            medium_term_context=medium_term,
            long_term_context=long_term,
            rag_context=rag_context,
            skill_context=skill_context,
            metadata_context=metadata,
            quality=quality,
            fusion_strategy=strategy,
            confidence=0.0,
            sources=sources
        )

    def _format_skill_context(self, skill_context: Dict[str, Any]) -> str:
        """格式化Skill上下文"""
        if not skill_context:
            return ""

        parts = ["【业务上下文】"]

        for skill_name, skill_data in list(skill_context.items())[-3:]:
            if isinstance(skill_data, dict):
                data = skill_data.get("data", {})
                if isinstance(data, dict):
                    summary_parts = []
                    for key, value in list(data.items())[:3]:
                        if isinstance(value, (str, int, float)):
                            summary_parts.append(f"{key}: {value}")
                    if summary_parts:
                        parts.append(f"• {skill_name}: {', '.join(summary_parts)}")

        return "\n".join(parts) if len(parts) > 1 else ""


class ContextRAGFusionLayer:
    """
    Context+RAG融合层 - 统一管理上下文和RAG的融合

    核心流程：
    1. ContextExtractor: 从SessionContext提取检索优化信息
    2. RAG检索: 使用增强的查询执行检索
    3. RAGResultInjector: 评估质量并注入到上下文
    4. AdaptiveFusionEngine: 选择融合策略并构建融合上下文
    5. 返回FusionResult供生成使用
    """

    def __init__(self, llm=None):
        self._lock = threading.Lock()
        self.context_extractor = ContextExtractor()
        self.rag_result_injector = RAGResultInjector()
        self.fusion_engine = AdaptiveFusionEngine()
        self._llm = llm
        self._intent_classifier = UnifiedIntentClassifier(llm=llm)

        self._context_strength_cache = {}
        logger.info("[ContextRAGFusionLayer] 初始化完成（统一意图分类器）")

    def process(
        self,
        query: str,
        session_context: SessionContext,
        rag_retrieval_func,
        intent: str = "general"
    ) -> FusionResult:
        """
        处理Context+RAG融合

        Args:
            query: 用户查询
            session_context: 会话上下文
            rag_retrieval_func: RAG检索函数
            intent: 意图类型

        Returns:
            FusionResult: 融合结果
        """
        start_time = time.time()

        with self._lock:
            result = self._intent_classifier.classify(query)
            llm_intent = result.intent.value
            llm_confidence = result.confidence
            llm_reasoning = result.reasoning
            logger.info(f"[FusionLayer] 意图: {llm_intent} (置信度: {llm_confidence:.2f})")
            logger.info(f"[FusionLayer] 推理: {llm_reasoning}")

            enhanced_query_obj = self.context_extractor.extract_for_rag(
                session_context, query
            )

            logger.info(f"[FusionLayer] 原始查询: '{query}'")
            logger.info(f"[FusionLayer] 增强查询: '{enhanced_query_obj.enhanced_query}'")
            logger.info(f"[FusionLayer] 实体: {enhanced_query_obj.entities}")

            retrieval_start = time.time()
            rag_result = rag_retrieval_func(
                query=enhanced_query_obj.enhanced_query,
                metadata_hints=enhanced_query_obj.metadata_hints
            )
            retrieval_time = time.time() - retrieval_start

            documents = rag_result.get("documents", [])
            quality, quality_confidence = self.rag_result_injector.evaluate_retrieval_quality(
                documents, query
            )

            injection_summary = self.rag_result_injector.inject_into_context(
                session_context, documents, query, quality, quality_confidence
            )

            short_term = self._extract_short_term(session_context)
            medium_term = self._extract_medium_term(session_context)
            long_term = self._extract_long_term(session_context)
            rag_context = self._format_rag_context(documents, quality)

            context_strength = self._calculate_context_strength(session_context)

            effective_intent = self._resolve_fusion_intent(query, llm_intent, intent)

            strategy, strategy_confidence = self.fusion_engine.select_strategy(
                quality, context_strength, effective_intent
            )

            fusion_ctx = self.fusion_engine.build_fusion_context(
                short_term=short_term,
                medium_term=medium_term,
                long_term=long_term,
                rag_context=rag_context,
                skill_context=session_context.skill_context,
                metadata=session_context.metadata,
                strategy=strategy,
                quality=quality
            )

            total_time = time.time() - start_time

            result = FusionResult(
                response="",
                quality=quality,
                fusion_strategy=strategy,
                confidence=strategy_confidence * quality_confidence,
                used_sources=fusion_ctx.sources,
                context_summary=self._generate_context_summary(
                    fusion_ctx, enhanced_query_obj, injection_summary
                ),
                metadata={
                    "original_query": query,
                    "enhanced_query": enhanced_query_obj.enhanced_query,
                    "retrieval_time": retrieval_time,
                    "total_process_time": total_time,
                    "entities": enhanced_query_obj.entities,
                    "injection_summary": injection_summary,
                    "context_strength": context_strength,
                    "classified_intent": llm_intent,
                    "effective_intent": effective_intent,
                    "retrieval_result": {
                        "success": rag_result.get("success", bool(documents)),
                        "documents": documents
                    },
                    "three_tier_context": (
                        session_context.get_three_tier_context()
                        if hasattr(session_context, "get_three_tier_context")
                        else {}
                    )
                }
            )

            logger.info(f"[FusionLayer] 处理完成: quality={quality.value}, "
                       f"strategy={strategy.value}, time={total_time:.3f}s")

            return result

    @staticmethod
    def _resolve_fusion_intent(query: str, classified_intent: str, fallback_intent: str) -> str:
        if classified_intent and classified_intent != "general":
            return classified_intent
        normalized = (query or "").strip().lower()
        if normalized in {"你好", "您好", "hello", "hi", "hey"}:
            return "greeting"
        if normalized in {"再见", "拜拜", "bye", "goodbye"}:
            return "farewell"
        return classified_intent or fallback_intent

    def _extract_short_term(self, context: SessionContext) -> str:
        """Extract short-term context."""
        if hasattr(context, "get_three_tier_context"):
            tier_context = context.get_three_tier_context()
            short_turns = tier_context.get("short_term_turns", [])
            if short_turns:
                parts = ["【当前对话】"]
                for turn in short_turns[-5:]:
                    role = "用户" if turn.get("role") == "user" else "助手"
                    content = turn.get("content", "")
                    content = content[:100] + "..." if len(content) > 100 else content
                    parts.append(f"{role}: {content}")
                return "\n".join(parts)

        recent_turns = [
            {"role": t.role, "content": t.content}
            for t in context.turn_history[-8:]
        ]

        if not recent_turns:
            return ""

        parts = ["【当前对话】"]
        for turn in recent_turns[-5:]:
            role = "用户" if turn["role"] == "user" else "助手"
            content = turn["content"][:100] + "..." if len(turn["content"]) > 100 else turn["content"]
            parts.append(f"{role}: {content}")

        return "\n".join(parts)

    def _extract_medium_term(self, context: SessionContext) -> str:
        """Extract medium-term compressed context."""
        if hasattr(context, "get_three_tier_context"):
            tier_context = context.get_three_tier_context()
            medium_summary = tier_context.get("medium_term_summary", "")
            if medium_summary:
                return f"【历史摘要】\n{medium_summary}"

        metadata = context.metadata
        discussed_products = metadata.get("discussed_products", [])

        if not discussed_products:
            return ""

        parts = ["【历史讨论】"]
        for product in discussed_products[-5:]:
            parts.append(f"- {product}")

        return "\n".join(parts)

    def _extract_long_term(self, context: SessionContext) -> str:
        """Extract long-term user profile context."""
        if hasattr(context, "get_three_tier_context"):
            tier_context = context.get_three_tier_context()
            long_term_text = tier_context.get("long_term_text", "")
            if long_term_text:
                return f"【用户背景】\n{long_term_text}"

        metadata = context.metadata

        parts = ["【用户背景】"]

        if metadata.get("customer_type"):
            parts.append(f"客户类型: {metadata['customer_type']}")

        if metadata.get("total_spent", 0) > 0:
            parts.append(f"累计消费: ￥{metadata['total_spent']:.2f}")

        return "\n".join(parts) if len(parts) > 1 else ""

    def _format_rag_context(
        self,
        documents: List[Dict[str, Any]],
        quality: RetrievalQuality
    ) -> str:
        """格式化RAG上下文"""
        if not documents:
            quality_messages = {
                RetrievalQuality.HIGH: "高质量检索完成",
                RetrievalQuality.MEDIUM: "检索到一般相关结果",
                RetrievalQuality.LOW: "检索结果相关性较低",
                RetrievalQuality.NONE: "未检索到相关文档"
            }
            return f"【知识库】\n{quality_messages.get(quality, '检索完成')}"

        parts = [f"【知识库】检索到 {len(documents)} 条相关信息"]

        for i, doc in enumerate(documents[:3], 1):
            content = doc.get("content", "")
            if len(content) > 150:
                content = content[:150] + "..."
            source = doc.get("source_file", "未知来源")
            parts.append(f"{i}. [{source}]\n   {content}")

        return "\n".join(parts)

    def _calculate_context_strength(self, context: SessionContext) -> float:
        """Calculate context strength with three-tier signals when available."""
        score = 0.0

        if hasattr(context, "get_three_tier_context"):
            tier_context = context.get_three_tier_context()
            stats = tier_context.get("stats", {})
            if stats.get("short_term_turns", 0) > 3:
                score += 0.3
            if stats.get("compressed_memories", 0) > 0:
                score += 0.2
            if tier_context.get("long_term_text"):
                score += 0.2
            if tier_context.get("intent_continuity"):
                score += 0.1

        if len(context.turn_history) > 3:
            score += 0.3

        if context.metadata.get("customer_type"):
            score += 0.2

        if context.metadata.get("current_product"):
            score += 0.2

        if context.skill_context:
            score += 0.2

        if len(context.turn_history) > 10:
            score += 0.1

        return min(score, 1.0)

    def _generate_context_summary(
        self,
        fusion_ctx: FusionContext,
        query_obj: ContextAwareQuery,
        injection_summary: Dict[str, Any]
    ) -> str:
        """生成上下文摘要"""
        summary_parts = [
            f"检索质量: {fusion_ctx.quality.value}",
            f"融合策略: {fusion_ctx.fusion_strategy.value}",
            f"置信度: {fusion_ctx.confidence:.2f}",
            f"数据源: {', '.join(fusion_ctx.sources)}"
        ]

        if query_obj.skill_context_applied:
            summary_parts.append("已应用Skill上下文")

        if injection_summary.get("entities_extracted"):
            entities = injection_summary["entities_extracted"][:3]
            summary_parts.append(f"提取实体: {', '.join(entities)}")

        return " | ".join(summary_parts)

    def get_fusion_prompt(
        self,
        fusion_result: FusionResult,
        system_prompt: str = ""
    ) -> str:
        """
        构建用于LLM生成的融合提示词

        Args:
            fusion_result: 融合结果
            system_prompt: 系统提示

        Returns:
            格式化的提示词
        """
        parts = []

        if system_prompt:
            parts.append(f"【系统指令】\n{system_prompt}\n")

        metadata = fusion_result.metadata
        parts.append(f"【检索信息】\n")
        parts.append(f"原始查询: {metadata.get('original_query', '')}\n")
        parts.append(f"检索质量: {fusion_result.quality.value}\n")
        parts.append(f"数据源: {', '.join(fusion_result.used_sources)}\n")

        if fusion_result.quality == RetrievalQuality.HIGH:
            parts.append("\n【重要】检索到了高质量文档，请优先基于检索结果回答\n")
        elif fusion_result.quality == RetrievalQuality.LOW:
            parts.append("\n【注意】检索结果相关性较低，请更多依赖对话上下文和你的知识\n")

        return "".join(parts)


context_rag_fusion_layer = ContextRAGFusionLayer()
