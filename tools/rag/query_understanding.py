"""
RAG 三层架构 - Layer 1: 查询理解层
支持 LLM 语义意图分类、实体提取、查询增强

核心改进：
1. LLM 语义意图分类 - 使用统一意图分类器
2. 更准确的实体提取
3. 智能查询增强
4. 动态复杂度评估
"""

import re
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field

from tools.rag.intent_classifier import (
    IntentType,
    IntentClassificationResult,
    UnifiedIntentClassifier,
    LLMIntentClassifier,
    IIntentClassifier,
    INTENT_DESCRIPTIONS
)


@dataclass
class QueryUnderstandingResult:
    """查询理解结果"""
    intent: str
    intent_confidence: float
    entities: Dict[str, List[str]]
    enhanced_query: str
    complexity: str
    intent_reasoning: str = ""

    @classmethod
    def from_classification_result(
        cls,
        classification: IntentClassificationResult,
        entities: Dict[str, List[str]],
        enhanced_query: str,
        complexity: str
    ) -> "QueryUnderstandingResult":
        return cls(
            intent=classification.intent.value,
            intent_confidence=classification.confidence,
            entities=entities,
            enhanced_query=enhanced_query,
            complexity=complexity,
            intent_reasoning=classification.reasoning
        )


class SemanticIntentClassifier:
    """Backward-compatible adapter for the previous semantic intent API."""

    def __init__(self, llm=None):
        self._classifier = LLMIntentClassifier(llm=llm)

    def classify(self, query: str) -> Tuple[str, float, str]:
        return self._classifier.classify(query).to_tuple()


class QueryUnderstandingLayer:
    """
    Layer 1: 查询理解层（统一版）

    职责：
    1. 意图分类 - 使用统一的 IntentClassifier
    2. 实体提取
    3. 查询增强
    4. 复杂度评估
    """

    PRODUCT_PATTERNS = [
        r'(?:智能)?手表',
        r'(?:无线|蓝牙)?耳机',
        r'(?:智能)?投影仪',
        r'(?:智能)?手机',
        r'(?:笔记本电脑?|笔记本)',
        r'(?:智能)?平板(?:电脑)?',
        r'智能(?:音箱|音响|音箱)',
        r'(?:智能)?手环',
    ]

    MODEL_PATTERN = r'([a-zA-Z]?\d+(?:\s*(?:Pro|Max|Plus|Air|Mini|SE|Ultra))?)'

    STOP_WORDS = {'的', '了', '是', '什么', '怎么', '多少', '吗', '呢', '吧', '啊', '请问', '我想', '一下'}

    COMPLEXITY_THRESHOLDS = {
        "simple": {"max_length": 20, "max_entities": 1, "max_score": 2},
        "medium": {"max_length": 50, "max_entities": 3, "max_score": 5},
        "complex": {"max_length": float('inf'), "max_entities": float('inf'), "max_score": float('inf')}
    }

    def __init__(self, llm=None, classifier: Optional[IIntentClassifier] = None):
        if classifier is None:
            self._classifier = UnifiedIntentClassifier(llm=llm)
        else:
            self._classifier = classifier

    def classify_intent(self, query: str) -> Tuple[str, float, str]:
        result = self._classifier.classify(query)
        return result.to_tuple()

    def extract_entities(self, query: str) -> Dict[str, List[str]]:
        entities = {
            "products": [],
            "models": [],
            "features": []
        }

        for pattern in self.PRODUCT_PATTERNS:
            matches = re.findall(pattern, query)
            entities["products"].extend(matches)

        model_matches = re.findall(self.MODEL_PATTERN, query, re.IGNORECASE)
        for model in model_matches:
            model_clean = model.strip().lower()
            if model_clean:
                entities["models"].append(model_clean)

        feature_keywords = [
            "续航", "屏幕", "音质", "拍照", "像素", "内存", "存储",
            "电池", "充电", "重量", "尺寸", "防水", "降噪"
        ]
        for feature in feature_keywords:
            if feature in query:
                entities["features"].append(feature)

        entities["products"] = list(set(entities["products"]))
        entities["models"] = list(set(entities["models"]))
        entities["features"] = list(set(entities["features"]))

        return entities

    def assess_complexity(self, query: str, entities: Dict[str, List[str]], intent: str) -> str:
        score = 0

        if len(query) > 80:
            score += 3
        elif len(query) > 50:
            score += 2
        elif len(query) > 25:
            score += 1

        entity_count = len(entities.get("products", [])) + len(entities.get("models", []))
        if entity_count > 3:
            score += 3
        elif entity_count > 1:
            score += 2
        elif entity_count > 0:
            score += 1

        if intent in ["comparison", "troubleshooting"]:
            score += 2
        elif intent == "recommendation":
            score -= 1

        if any(kw in query for kw in ["详细", "具体", "完全", "所有", "全面"]):
            score += 2

        if "还有" in query or "另外" in query:
            score += 1

        if score >= 5:
            return "complex"
        elif score >= 3:
            return "medium"
        return "simple"

    def enhance_query(self, query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        if not chat_history or len(chat_history) == 0:
            return query

        context_parts = []
        recent_turns = chat_history[-3:] if len(chat_history) > 3 else chat_history

        for turn in recent_turns:
            role = turn.get("role", "")
            content = turn.get("content", "")

            if role == "user":
                entities = self.extract_entities(content)
                if entities["models"]:
                    context_parts.extend(entities["models"])
            elif role == "assistant":
                model_matches = re.findall(self.MODEL_PATTERN, content, re.IGNORECASE)
                context_parts.extend([m.strip().lower() for m in model_matches if m.strip()])

        if not context_parts:
            return query

        context_unique = list(dict.fromkeys(context_parts))

        if any(model.lower() in query.lower() for model in context_unique):
            return query

        enhanced = query
        if context_unique:
            enhanced += " " + " ".join(context_unique[:3])

        return enhanced

    def process(self, query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> QueryUnderstandingResult:
        classification = self._classifier.classify(query)
        entities = self.extract_entities(query)
        enhanced_query = self.enhance_query(query, chat_history)
        complexity = self.assess_complexity(query, entities, classification.intent.value)

        return QueryUnderstandingResult.from_classification_result(
            classification=classification,
            entities=entities,
            enhanced_query=enhanced_query,
            complexity=complexity
        )


query_understanding_layer = QueryUnderstandingLayer()
