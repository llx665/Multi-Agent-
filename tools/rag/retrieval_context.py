"""
RAG 三层架构 - Layer 2: 检索层
负责 Self-RAG 决策、混合搜索、Adaptive top_k
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import time


@dataclass
class RetrievalResult:
    """检索结果"""
    decision: str  # "retrieval", "no_retrieval", "failed"
    documents: List[Dict[str, Any]]
    adaptive_top_k: int
    complexity: str
    confidence: float
    hybrid_applied: bool
    rerank_applied: bool
    retrieval_time: float
    reasoning: str


class RetrievalLayer:
    """
    Layer 2: 检索层

    职责：
    1. Self-RAG 决策 (是否检索、检索多少)
    2. Adaptive top_k (根据意图和复杂度调整)
    3. Hybrid Search (向量 + BM25, RRF 融合)
    4. Rerank 重排序 (Cross-Encoder)
    """

    # 意图到 top_k 的映射
    INTENT_TOP_K = {
        "price_inquiry": 3,
        "product_spec": 4,
        "comparison": 6,
        "troubleshooting": 5,
        "purchase": 3,
        "recommendation": 3,
        "general": 2
    }

    # 复杂度调整因子
    COMPLEXITY_FACTOR = {
        "simple": 0.8,
        "medium": 1.0,
        "complex": 1.3
    }

    def __init__(self, rag_tool):
        """
        Args:
            rag_tool: RAGTool 实例，用于执行实际检索
        """
        self._rag_tool = rag_tool

    def adaptive_top_k(self, intent: str, complexity: str, base_k: int = 5) -> int:
        """
        根据意图和复杂度自适应 top_k

        Args:
            intent: 意图类型
            complexity: 复杂度 (simple/medium/complex)
            base_k: 基础 top_k

        Returns:
            调整后的 top_k
        """
        # 获取意图基础值
        intent_k = self.INTENT_TOP_K.get(intent, 3)

        # 获取复杂度因子
        complexity_factor = self.COMPLEXITY_FACTOR.get(complexity, 1.0)

        # 计算最终值
        final_k = int(intent_k * complexity_factor)

        # 限制范围
        return max(1, min(final_k, 15))

    def decide_retrieval(self, query: str, llm, intent: str = None) -> Dict[str, Any]:
        """
        Self-RAG 决策

        Args:
            query: 查询
            llm: LLM 实例
            intent: 可选的意图类型

        Returns:
            决策结果字典
        """
        if not llm:
            return {
                "need_retrieval": True,
                "confidence": 0.5,
                "reason": "No LLM provided, default to retrieval",
                "complexity": "medium",
                "adaptive_top_k": self.INTENT_TOP_K.get(intent, 3)
            }

        try:
            decision = self._rag_tool.self_rag_decision(query, llm)
            return decision
        except Exception as e:
            return {
                "need_retrieval": True,
                "confidence": 0.0,
                "reason": f"Self-RAG decision failed: {str(e)}",
                "complexity": "medium",
                "adaptive_top_k": self.INTENT_TOP_K.get(intent, 3)
            }

    def execute(
        self,
        query: str,
        top_k: int,
        llm=None,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        chat_history: List[Dict[str, str]] = None,
        intent: str = None,
        complexity: str = "medium"
    ) -> RetrievalResult:
        """
        执行检索

        Args:
            query: 查询
            top_k: 基础 top_k
            llm: LLM 实例
            use_hybrid: 是否使用混合检索
            use_rerank: 是否使用重排序
            chat_history: 对话历史
            intent: 意图类型
            complexity: 复杂度

        Returns:
            RetrievalResult 对象
        """
        start_time = time.time()

        # 1. Self-RAG 决策
        decision = self.decide_retrieval(query, llm, intent)

        if not decision.get("need_retrieval", True):
            return RetrievalResult(
                decision="no_retrieval",
                documents=[],
                adaptive_top_k=0,
                complexity=decision.get("complexity", "medium"),
                confidence=decision.get("confidence", 0.0),
                hybrid_applied=False,
                rerank_applied=False,
                retrieval_time=time.time() - start_time,
                reasoning=decision.get("reason", "Decision: no retrieval needed")
            )

        # 2. 自适应 top_k
        adaptive_k = decision.get("adaptive_top_k", top_k)
        if intent:
            adaptive_k = self.adaptive_top_k(intent, complexity, adaptive_k)

        # 3. 执行检索
        try:
            result = self._rag_tool.retrieve(
                query=query,
                top_k=adaptive_k,
                enable_self_rag=False,  # 已经在 decide_retrieval 中决策过
                llm=None,  # 已经在 decide_retrieval 中决策过
                use_cache=True,
                use_hybrid=use_hybrid,
                use_rerank=use_rerank,
                chat_history=chat_history
            )

            return RetrievalResult(
                decision="retrieval",
                documents=result.get("documents", []),
                adaptive_top_k=adaptive_k,
                complexity=decision.get("complexity", "medium"),
                confidence=decision.get("confidence", 0.0),
                hybrid_applied=result.get("hybrid_applied", False),
                rerank_applied=result.get("rerank_applied", False),
                retrieval_time=time.time() - start_time,
                reasoning=f"Retrieved {len(result.get('documents', []))} documents"
            )

        except Exception as e:
            return RetrievalResult(
                decision="failed",
                documents=[],
                adaptive_top_k=adaptive_k,
                complexity=decision.get("complexity", "medium"),
                confidence=0.0,
                hybrid_applied=False,
                rerank_applied=False,
                retrieval_time=time.time() - start_time,
                reasoning=f"Retrieval failed: {str(e)}"
            )

    def hybrid_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """
        执行混合检索 (向量 + BM25)

        注意: 此方法直接调用 RAGTool 的检索方法
        """
        try:
            result = self._rag_tool.retrieve(
                query=query,
                top_k=top_k,
                enable_self_rag=False,
                llm=None,
                use_cache=False,
                use_hybrid=True,
                use_rerank=False,
                chat_history=None
            )
            return result.get("documents", [])
        except Exception:
            return []

    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """
        执行重排序

        Args:
            query: 查询
            documents: 文档列表
            top_k: 返回数量

        Returns:
            重排序后的文档列表
        """
        if not documents or not self._rag_tool.reranker:
            return documents[:top_k]

        try:
            reranked = self._rag_tool.reranker.rerank(query, documents, top_k)
            return reranked
        except Exception:
            return documents[:top_k]


# 全局单例工厂函数
def create_retrieval_layer(rag_tool) -> RetrievalLayer:
    """创建检索层实例"""
    return RetrievalLayer(rag_tool)