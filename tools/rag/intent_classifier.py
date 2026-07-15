"""
意图分类核心模块
================

统一的意图分类系统，解决代码重复问题。

核心设计：
1. IntentType 枚举 - 7种标准意图类型
2. IntentClassificationResult - 统一的分类结果数据结构
3. IIntentClassifier 接口 - 抽象基类
4. UnifiedIntentClassifier - 支持LLM和关键词回退的统一实现
5. IntentClassifierFactory - 工厂函数创建分类器

使用方式：
    from tools.rag.intent_classifier import UnifiedIntentClassifier

    classifier = UnifiedIntentClassifier(llm)
    result = classifier.classify("推荐一款蓝牙耳机")
    # result.intent = "recommendation"
    # result.confidence = 0.95
    # result.reasoning = "用户请求推荐产品"
"""

import re
import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field


class IntentType(Enum):
    """标准意图类型枚举"""
    PRICE_INQUIRY = "price_inquiry"
    PRODUCT_SPEC = "product_spec"
    COMPARISON = "comparison"
    TROUBLESHOOTING = "troubleshooting"
    PURCHASE = "purchase"
    RECOMMENDATION = "recommendation"
    GENERAL = "general"


INTENT_DESCRIPTIONS: Dict[IntentType, str] = {
    IntentType.PRICE_INQUIRY: "用户询问产品价格、优惠、折扣、性价比相关的问题",
    IntentType.PRODUCT_SPEC: "用户询问产品规格、参数、功能、性能、配置相关的问题",
    IntentType.COMPARISON: "用户对比两个或多个产品，询问区别、差异、哪个更好",
    IntentType.TROUBLESHOOTING: "用户遇到产品问题、故障，寻求解决方案或技术支持",
    IntentType.PURCHASE: "用户有明确的购买意向，询问如何购买、下单、订购",
    IntentType.RECOMMENDATION: "用户请求推荐产品、寻求购买建议，但不一定是购买",
    IntentType.GENERAL: "用户进行一般性对话、问候、或无法归类的查询"
}

INTENT_KEYWORDS: Dict[IntentType, Dict[str, Any]] = {
    IntentType.PRICE_INQUIRY: {
        "keywords": ["价格", "多少钱", "便宜", "贵", "优惠", "折扣", "cost", "price", "报价", "性价比"],
        "weight": 1.0
    },
    IntentType.PRODUCT_SPEC: {
        "keywords": ["参数", "配置", "规格", "功能", "spec", "specification", "性能", "续航", "屏幕"],
        "weight": 1.0
    },
    IntentType.COMPARISON: {
        "keywords": ["对比", "比较", "哪个好", "区别", "差异", "不同", "compare", "difference", "和", "与"],
        "weight": 1.0
    },
    IntentType.TROUBLESHOOTING: {
        "keywords": ["问题", "故障", "坏了", "不行", "error", "issue", "维修", "售后", "解决"],
        "weight": 1.0
    },
    IntentType.PURCHASE: {
        "keywords": ["买", "下单", "购买", "order", "buy", "订购", "入手"],
        "weight": 1.0
    },
    IntentType.RECOMMENDATION: {
        "keywords": ["推荐", "建议", "有什么好", "有什么好用的", "有什么推荐", "哪款比较好", "什么值得买", "给个建议"],
        "weight": 1.2
    },
    IntentType.GENERAL: {
        "keywords": [],
        "weight": 0.0
    }
}


@dataclass
class IntentClassificationResult:
    """统一的意图分类结果"""
    intent: IntentType
    confidence: float
    reasoning: str
    matched_keywords: List[str] = field(default_factory=list)
    method: str = "unknown"

    def to_tuple(self) -> Tuple[str, float, str]:
        """转换为兼容旧接口的元组"""
        return self.intent.value, self.confidence, self.reasoning

    def __str__(self) -> str:
        return f"IntentClassificationResult(intent={self.intent.value}, confidence={self.confidence:.2f}, method={self.method})"


class IIntentClassifier(ABC):
    """意图分类器抽象接口"""

    @abstractmethod
    def classify(self, query: str) -> IntentClassificationResult:
        """
        对查询进行意图分类

        Args:
            query: 用户查询

        Returns:
            IntentClassificationResult
        """
        pass

    @abstractmethod
    def classify_batch(self, queries: List[str]) -> List[IntentClassificationResult]:
        """批量分类"""
        pass


class KeywordIntentClassifier(IIntentClassifier):
    """
    基于关键词的意图分类器

    使用预定义的关键词模式进行意图分类
    """

    def __init__(
        self,
        keywords: Optional[Dict[IntentType, Dict[str, Any]]] = None,
        case_sensitive: bool = False
    ):
        self.keywords = keywords or INTENT_KEYWORDS
        self.case_sensitive = case_sensitive

    def classify(self, query: str) -> IntentClassificationResult:
        query_text = query if self.case_sensitive else query.lower()

        intent_scores: Dict[IntentType, Tuple[float, List[str]]] = {}

        for intent, config in self.keywords.items():
            if intent == IntentType.GENERAL:
                continue

            score = 0.0
            matched = []

            for keyword in config["keywords"]:
                search_text = keyword if self.case_sensitive else keyword.lower()
                if search_text in query_text:
                    score += config["weight"]
                    matched.append(keyword)

            if score > 0:
                intent_scores[intent] = (score, matched)

        if not intent_scores:
            return IntentClassificationResult(
                intent=IntentType.GENERAL,
                confidence=0.5,
                reasoning="无匹配关键词，识别为通用查询",
                method="keyword"
            )

        best_intent = max(intent_scores, key=lambda x: intent_scores[x][0])
        score, matched = intent_scores[best_intent]
        confidence = min(0.95, score / 2.0)

        return IntentClassificationResult(
            intent=best_intent,
            confidence=confidence,
            reasoning=f"匹配关键词: {', '.join(matched[:3])}",
            matched_keywords=matched,
            method="keyword"
        )

    def classify_batch(self, queries: List[str]) -> List[IntentClassificationResult]:
        return [self.classify(q) for q in queries]


class LLMIntentClassifier(IIntentClassifier):
    """
    基于 LLM 的意图分类器

    使用 LLM 进行语义意图分类，失败时回退到关键词匹配
    """

    INTENT_LIST_PROMPT = "\n".join([
        f"- {intent.value}: {desc}"
        for intent, desc in INTENT_DESCRIPTIONS.items()
    ])

    CLASSIFICATION_PROMPT_TEMPLATE = """你是一个专业的电商客服意图分类器。

用户查询: "{query}"

请根据查询的语义内容，判断用户意图。可选的意图类型：

{intent_list}

判断规则：
1. "推荐"、"建议"、"有什么好"、"有什么好用的"、"有什么推荐"、"哪款比较好" 是 recommendation
2. "XX和XX哪个好"、"XX和XX区别"、"XX与XX对比" 是 comparison
3. "多少钱"、"价格多少"、"便宜多少" 是 price_inquiry
4. "参数"、"配置"、"规格"、"功能"、"spec" 是 product_spec
5. "坏了"、"问题"、"故障"、"怎么解决" 是 troubleshooting
6. "买"、"下单"、"购买"、"订购" 是 purchase
7. 简单问候或无法归类的是 general

重要：
- "推荐一个XX" 是 recommendation，不是 comparison
- "哪个好" 如果是请求推荐，就是 recommendation
- "XX和XX哪个好" 如果是请求推荐其中一个，是 recommendation
- "XX和XX有什么区别" 是 comparison

请按以下 JSON 格式返回：
{{
    "intent": "意图类型",
    "confidence": 0.0-1.0之间的置信度,
    "reasoning": "你的判断理由（1-2句话）"
}}

示例：
- 查询: "推荐一个投影仪" → {{"intent": "recommendation", "confidence": 0.95, "reasoning": "用户明确请求推荐产品"}}
- 查询: "X12多少钱" → {{"intent": "price_inquiry", "confidence": 0.92, "reasoning": "用户询问价格"}}
- 查询: "你好" → {{"intent": "general", "confidence": 0.88, "reasoning": "简单问候"}}
"""

    def __init__(
        self,
        llm: Any = None,
        fallback_classifier: Optional[IIntentClassifier] = None,
        logger: Optional[Any] = None
    ):
        self._llm = llm
        self._fallback = fallback_classifier or KeywordIntentClassifier()
        self._logger = logger

    def _log(self, level: str, message: str):
        if self._logger:
            getattr(self._logger, level)(message)

    def classify(self, query: str) -> IntentClassificationResult:
        if self._llm is None:
            return self._fallback.classify(query)

        try:
            return self._llm_based_classify(query)
        except Exception as e:
            self._log("warning", f"[LLMIntentClassifier] LLM 分类失败: {e}")
            return self._fallback.classify(query)

    def _llm_based_classify(self, query: str) -> IntentClassificationResult:
        prompt = self.CLASSIFICATION_PROMPT_TEMPLATE.format(
            query=query,
            intent_list=self.INTENT_LIST_PROMPT
        )

        response = self._llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            self._log("warning", f"[LLMIntentClassifier] 无法解析 LLM 响应 JSON")
            return self._fallback.classify(query)

        result = json.loads(json_match.group())
        intent_str = result.get("intent", "general")
        confidence = float(result.get("confidence", 0.5))
        reasoning = result.get("reasoning", "")

        try:
            intent = IntentType(intent_str)
        except ValueError:
            intent = IntentType.GENERAL

        self._log("info", f"[LLMIntentClassifier] 分类成功: {intent.value} ({confidence:.2f})")

        return IntentClassificationResult(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            method="llm"
        )

    def classify_batch(self, queries: List[str]) -> List[IntentClassificationResult]:
        return [self.classify(q) for q in queries]


class UnifiedIntentClassifier(IIntentClassifier):
    """
    统一意图分类器

    优先使用 LLM 分类，LLM 不可用时自动回退到关键词匹配
    支持内存缓存和 Redis 缓存
    """

    def __init__(
        self,
        llm: Any = None,
        use_memory_cache: bool = True,
        use_redis_cache: bool = True,
        cache_ttl: int = 300
    ):
        self._llm_classifier = LLMIntentClassifier(llm=llm)
        self._keyword_classifier = KeywordIntentClassifier()
        self._use_memory_cache = use_memory_cache
        self._use_redis_cache = use_redis_cache
        self._cache_ttl = cache_ttl
        self._memory_cache: Dict[str, IntentClassificationResult] = {}
        self._redis_cache = None
        self._init_redis_cache()

    def _init_redis_cache(self):
        """初始化 Redis 缓存"""
        if self._use_redis_cache:
            try:
                from tools.rag.redis_cache_manager import get_cache_manager, IntentClassificationCache
                cache_manager = get_cache_manager()
                if cache_manager.is_available:
                    self._redis_cache = IntentClassificationCache(cache_manager)
            except Exception:
                self._redis_cache = None

    def classify(self, query: str) -> IntentClassificationResult:
        cache_key = query.strip().lower()

        # 1. 尝试从内存缓存获取
        if self._use_memory_cache and cache_key in self._memory_cache:
            cached = self._memory_cache[cache_key]
            return IntentClassificationResult(
                intent=cached.intent,
                confidence=cached.confidence,
                reasoning=cached.reasoning + " [memory_cached]",
                method=cached.method + "+memory_cache"
            )

        # 2. 尝试从 Redis 缓存获取
        if self._redis_cache:
            try:
                cached = self._redis_cache.get_intent(query)
                if cached:
                    result = IntentClassificationResult(
                        intent=IntentType(cached["intent"]),
                        confidence=cached["confidence"],
                        reasoning=cached["reasoning"] + " [redis_cached]",
                        method="llm+redis_cache" if cached.get("intent") else "keyword+redis_cache"
                    )
                    self._memory_cache[cache_key] = result
                    return result
            except Exception:
                pass

        # 3. 执行实际分类
        if self._llm_classifier._llm is not None:
            result = self._llm_classifier.classify(query)
        else:
            result = self._keyword_classifier.classify(query)

        # 4. 缓存结果
        if self._use_memory_cache:
            self._memory_cache[cache_key] = result

        if self._redis_cache:
            try:
                self._redis_cache.set_intent(
                    query=query,
                    intent=result.intent.value,
                    confidence=result.confidence,
                    reasoning=result.reasoning,
                    ttl=self._cache_ttl
                )
            except Exception:
                pass

        return result

    def classify_batch(self, queries: List[str]) -> List[IntentClassificationResult]:
        return [self.classify(q) for q in queries]

    def clear_cache(self):
        self._memory_cache.clear()
        if self._redis_cache:
            try:
                from tools.rag.redis_cache_manager import CacheType
                cache_manager = get_cache_manager()
                if cache_manager.is_available:
                    cache_manager.clear_type(CacheType.INTENT)
            except Exception:
                pass

    def get_memory_cache_size(self) -> int:
        return len(self._memory_cache)


def create_intent_classifier(
    llm: Any = None,
    method: str = "unified",
    use_memory_cache: bool = True,
    use_redis_cache: bool = True,
    cache_ttl: int = 300
) -> IIntentClassifier:
    """
    工厂函数：创建意图分类器

    Args:
        llm: LLM 实例
        method: 分类方法 ("unified", "llm", "keyword")
        use_memory_cache: 是否使用内存缓存
        use_redis_cache: 是否使用 Redis 缓存
        cache_ttl: 缓存过期时间（秒）

    Returns:
        IIntentClassifier 实例
    """
    if method == "keyword":
        return KeywordIntentClassifier()
    elif method == "llm":
        return LLMIntentClassifier(llm=llm)
    else:
        return UnifiedIntentClassifier(
            llm=llm,
            use_memory_cache=use_memory_cache,
            use_redis_cache=use_redis_cache,
            cache_ttl=cache_ttl
        )


def get_all_intent_types() -> List[IntentType]:
    """获取所有意图类型"""
    return list(IntentType)


def get_intent_description(intent: IntentType) -> str:
    """获取意图类型描述"""
    return INTENT_DESCRIPTIONS.get(intent, "")
