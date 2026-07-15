"""
Supervisor Agent
负责任务路由和结果整合的调度中心

关键设计：
1. LLM 驱动的意图分类（替代关键词匹配）
2. 全异步架构（避免 asyncio.run() 阻塞事件循环）
3. 基于规则的兜底机制（关键词备用）
"""

import json
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from agents.agent_state_graph import AgentGraphState, NodeExecutionPolicy, StateGraphExecutor
from core.logger import LoggerManager
from core.session_context import SessionContext
from core.agent_factory import agent_factory
from core.rate_limiter import LLMRateLimiter
from skills.manager import SkillManager
from skills.base import SkillResult
from tools.rag.fallback_policy import plan_low_quality_rag_fallback

logger = LoggerManager.get_logger("supervisor_agent")

# 全局限流器
_llm_rate_limiter = LLMRateLimiter(max_concurrent=5, requests_per_minute=30)


# Prompt 模板
RAG_RESULT_REPHRASE_PROMPT = """你是一个热情的客服助手。用户从知识库查询到了相关信息，请用自然、口语化的方式重新组织这些内容回复用户。

要求：
1. 语言要自然、口语化，像朋友聊天一样
2. 不要直接说"根据知识库"或"查询显示"
3. 不要直接复制原文，要用你自己的话总结
4. 如果内容太长，提取最关键的信息
5. 可以适当添加语气词，让回复更亲切
6. 结尾可以问问用户是否还需要其他帮助

用户问题：{query}

知识库内容：
{content}

请用口语化的方式回复用户："""

INTENT_CLASSIFICATION_PROMPT = """你是一个智能客服系统的意图分类器。

请分析以下用户问题的意图，从以下类别中选择一个最合适的：
- sales: 产品咨询、价格查询、购买推荐、优惠询问、产品详情（如：推荐产品、询问价格、详细介绍、这款、那款）
- tech_support: 产品使用指导、故障排查、技术问题解决（如：怎么用、坏了、连不上）
- negotiation: 价格谈判、优惠申请、折扣讨论（如：便宜点、能不能打折）
- greeting: 问候、闲聊（如：你好、在吗、hello）
- farewell: 告别、感谢（如：再见、拜拜、谢谢、感谢）- 注意：形容词"好的"不属于此类
- general: 其他问题

用户问题：{query}

历史上下文：{history}

请返回 JSON 格式的分类结果：
{{
    "intent": "分类意图",
    "confidence": 0.0-1.0之间的置信度,
    "reason": "分类理由"
}}

重要规则：
1. 如果历史中有产品推荐（如"给您推荐3款耳机"），用户询问"第二款"、"详细介绍"、"说说这个"等，应归类为 sales
2. 如果用户询问产品、推荐、价格，即使包含"好的"等形容词，也应归类为 sales
3. farewell 仅适用于明确的告别场景（再见、拜拜、谢谢等）
4. 置信度反映分类的确定程度
5. 如果是混合意图，选择最主要的一个"""


class SupervisorAgent:
    """
    Supervisor Agent - 任务调度中心

    职责：
    1. LLM 意图识别（Intent Classification）
    2. 任务路由（Task Routing）
    3. 结果整合（Result Integration）
    """

    def __init__(
        self,
        skill_manager: Optional[SkillManager] = None,
        agent_factory_instance: Optional[Any] = None,
        llm: Optional[Any] = None,
    ):
        self.skill_manager = skill_manager or SkillManager()
        self.agent_factory = agent_factory_instance or agent_factory
        self._llm = llm
        logger.info("[SupervisorAgent] 初始化完成")

    def _get_llm(self):
        """获取 LLM 实例（延迟初始化）"""
        if self._llm is None:
            self._llm = agent_factory.get_llm()
        return self._llm

    def _get_streaming_llm(self):
        """获取 LLM 实例（与 _get_llm 相同实例，streaming=True 兼容 ainvoke 和 astream）"""
        return self._get_llm()

    # ============ LLM 驱动的意图分类 ============

    def _build_state_graph(self) -> StateGraphExecutor:
        graph = StateGraphExecutor()
        policy = NodeExecutionPolicy(timeout_seconds=30.0, retries=1, fallback=self._node_fallback)

        # DAG dependency layout:
        #   intent ──→ plan ──→ execute ──→ verify ──→ replan ──→ final
        #              ↑
        #   retrieve ──┘  (plan + retrieve run in parallel after intent)
        graph.add_node("intent", self._graph_intent_node, policy, depends_on=set())
        graph.add_node("plan", self._graph_plan_node, policy, depends_on={"intent"})
        graph.add_node("retrieve", self._graph_retrieve_node, policy, depends_on={"intent"})
        graph.add_node("execute", self._graph_execute_node, policy, depends_on={"plan"})
        graph.add_node("verify", self._graph_verify_node, policy, depends_on={"execute", "retrieve"})
        graph.add_node("replan", self._graph_replan_node, policy, depends_on={"verify"})
        graph.add_node("final", self._graph_final_node, policy, depends_on={"replan"})
        return graph

    async def _node_fallback(self, state: AgentGraphState, error: Exception) -> AgentGraphState:
        state.metadata.setdefault("fallbacks", []).append(
            {"node": "agent_graph", "error": type(error).__name__}
        )
        if not state.final_response:
            state.final_response = {
                "success": False,
                "message": "抱歉，当前任务处理失败，请稍后重试。",
                "intent": state.intent or "error",
                "intent_confidence": state.confidence,
                "evaluation_score": 0.0,
            }
        return state

    async def _graph_intent_node(self, state: AgentGraphState) -> AgentGraphState:
        intent, confidence = await self.classify_intent_llm(state.query, state.context.turn_history)
        state.intent = intent
        state.confidence = confidence
        self._last_intent_confidence = confidence
        return state

    async def _graph_plan_node(self, state: AgentGraphState) -> AgentGraphState:
        state.plan = {
            "intent": state.intent,
            "nodes": ["intent", "plan", "retrieve", "execute", "verify", "replan", "final"],
        }
        return state

    async def _graph_retrieve_node(self, state: AgentGraphState) -> AgentGraphState:
        if state.intent != "general":
            state.retrieval_result = {
                "success": True,
                "documents": [],
                "has_relevant_info": False,
                "skipped": True,
                "reason": "intent_does_not_require_prefetch",
            }
            state.metadata["retrieval"] = {
                "source": "state_graph",
                "document_count": 0,
                "skipped": True,
            }
            return state

        # Reuse prefetched RAG result from chat_service_v3 to avoid
        # performing a duplicate retrieval.
        prefetched = state.context.metadata.get("prefetched_rag_result")
        if prefetched and prefetched.get("query") == state.query:
            documents = prefetched.get("documents", [])
            source = prefetched.get("source", "prefetch")
            logger.info(f"[SupervisorAgent] 复用预取RAG结果 (source={source}), "
                        f"documents={len(documents)}")
        else:
            documents = await self._query_knowledge_base_async(state.query, state.context)

        state.retrieval_result = {
            "success": True,
            "documents": documents,
            "has_relevant_info": bool(documents),
            "query": state.query,
        }
        state.rag_fallback = plan_low_quality_rag_fallback(
            state.query,
            state.retrieval_result,
            quality="high" if documents else "none",
        )
        state.context.metadata["prefetched_rag_result"] = state.retrieval_result
        if state.rag_fallback.get("needed"):
            state.context.metadata["rag_fallback"] = state.rag_fallback
            state.metadata["rag_fallback"] = state.rag_fallback
        state.metadata["retrieval"] = {
            "source": "state_graph",
            "document_count": len(documents),
            "has_relevant_info": bool(documents),
        }
        return state

    async def _graph_execute_node(self, state: AgentGraphState) -> AgentGraphState:
        state.routing_results = await self.route_task(state.intent or "general", state.query, state.context)
        return state

    async def _graph_verify_node(self, state: AgentGraphState) -> AgentGraphState:
        business_success = any(
            name != "customer_classifier" and result and result.success
            for name, result in state.routing_results
        )
        state.needs_replan = bool(state.rag_fallback.get("needed")) or not business_success
        state.metadata["verification"] = {
            "needs_replan": state.needs_replan,
            "result_count": len(state.routing_results),
            "business_success": business_success,
        }
        return state

    async def _graph_replan_node(self, state: AgentGraphState) -> AgentGraphState:
        if state.needs_replan:
            rewrite_query = state.rag_fallback.get("rewrite_query") if state.rag_fallback else None
            if rewrite_query:
                retry_documents = await self._query_knowledge_base_async(rewrite_query, state.context)
                state.metadata["replanned"] = {
                    "strategy": "rewrite_retry",
                    "query": rewrite_query,
                    "document_count": len(retry_documents),
                }
                if retry_documents:
                    state.retrieval_result = {
                        "success": True,
                        "documents": retry_documents,
                        "has_relevant_info": True,
                        "query": rewrite_query,
                        "source": "replan_rewrite",
                    }
                    state.context.metadata["prefetched_rag_result"] = state.retrieval_result
                    rephrased_response = await self._format_rag_response(retry_documents, rewrite_query)
                    state.routing_results = [
                        (name, result)
                        for name, result in state.routing_results
                        if name == "customer_classifier"
                    ]
                    state.routing_results.append(
                        (
                            "general_replan",
                            SkillResult(
                                success=True,
                                data={
                                    "intent": "general",
                                    "response": rephrased_response,
                                    "sources": ["knowledge_base"],
                                    "replan_query": rewrite_query,
                                },
                                message="rewrite retry succeeded",
                                confidence=0.7,
                            ),
                        )
                    )
                    return state

            state.routing_results = [
                (
                    "fallback",
                    SkillResult(
                        success=True,
                        data={"message": "抱歉，当前信息不足，请补充更多细节后我再继续处理。"},
                        message="fallback clarification",
                        confidence=0.3,
                    ),
                )
            ]
            state.metadata["replanned"] = {
                "strategy": "clarification",
                "document_count": 0,
            }
        return state

    async def _graph_final_node(self, state: AgentGraphState) -> AgentGraphState:
        state.final_response = await self._integrate_results_async(
            state.intent or "general",
            state.routing_results,
            state.context,
            state.confidence,
        )
        return state

    async def classify_intent_llm(
        self,
        query: str,
        history: List[Dict] = None
    ) -> Tuple[str, float]:
        """
        使用 LLM 进行意图分类

        Args:
            query: 用户查询
            history: 对话历史

        Returns:
            (意图类型, 置信度)
        """
        try:
            # 构建历史上下文
            history_text = ""
            if history and len(history) > 0:
                recent = history[-6:]
                history_text = "\n".join([
                    f"{'用户' if h.role == 'user' else '助手'}: {h.content[:50] if h.content else ''}"
                    for h in recent
                ])
            else:
                history_text = "（无历史记录）"

            # 构建 Prompt
            prompt = INTENT_CLASSIFICATION_PROMPT.format(
                query=query,
                history=history_text
            )

            # 调用 LLM（通过限流器）
            llm = self._get_llm()
            async with _llm_rate_limiter:
                response = await llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            # 解析 JSON 响应（增强容错）
            raw_content = content.strip()

            # 尝试移除 Markdown 代码块包裹
            if raw_content.startswith("```"):
                # 找到第一个 ``` 之后和最后一个 ``` 之前的内容
                lines = raw_content.split('\n')
                # 检查是否有语言标识（如 ```json）
                if len(lines) >= 2 and lines[0].startswith("```"):
                    # 去掉第一行（```json）和最后一行（```）
                    raw_content = '\n'.join(lines[1:-1]) if lines[-1].strip() == "```" else '\n'.join(lines[1:])
                raw_content = raw_content.strip()

            # 尝试提取 JSON 对象（处理前后有额外文字的情况）
            import re
            # 尝试直接解析（最常见情况）
            try:
                result = json.loads(raw_content)
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试用正则提取第一个 JSON 对象
                try:
                    json_match = re.search(r'\{[\s\S]*\}', raw_content)
                    if json_match:
                        json_str = json_match.group()
                        result = json.loads(json_str)
                    else:
                        raise json.JSONDecodeError("No JSON object found", raw_content, 0)
                except json.JSONDecodeError as e:
                    # 记录原始响应以便调试
                    logger.warning(
                        f"[SupervisorAgent] LLM 响应 JSON 解析失败，已使用规则兜底处理。\n"
                        f"    原始响应内容: {raw_content[:500]}{'...(truncated)' if len(raw_content) > 500 else ''}\n"
                        f"    解析错误: {e}"
                    )
                    raise

            intent = result.get("intent", "general").lower()
            confidence = float(result.get("confidence", 0.5))

            logger.info(
                f"[SupervisorAgent] LLM意图识别: {intent} "
                f"(置信度: {confidence:.2f}), 原因: {result.get('reason', 'N/A')}"
            )

            return intent, confidence

        except json.JSONDecodeError:
            logger.warning(f"[SupervisorAgent] LLM 响应 JSON 解析失败，使用规则兜底")
            return self._classify_intent_fallback(query, history)
        except Exception as e:
            logger.error(f"[SupervisorAgent] LLM 意图分类失败: {e}，使用规则兜底")
            return self._classify_intent_fallback(query, history)

    def _classify_intent_fallback(
        self,
        query: str,
        history: List[Dict] = None
    ) -> Tuple[str, float]:
        """
        基于规则的意图分类（兜底机制）

        Args:
            query: 用户查询
            history: 对话历史

        Returns:
            (意图类型, 置信度)
        """
        query_lower = query.lower()

        # 意图关键词映射
        INTENT_KEYWORDS = {
            "sales": [
                "买", "多少钱", "价格", "推荐", "产品", "优惠", "商品",
                "折扣", "促销", "购买", "订购", "性价比", "划算",
                "手机", "电脑", "平板", "耳机", "手表", "鼠标", "键盘", "投影仪",
                # 产品详情相关
                "介绍", "详细介绍", "详细说说", "详情", "参数", "配置", "功能",
                "第一款", "第二款", "第三款", "第一款", "哪款", "这款", "那个",
            ],
            "tech_support": [
                "怎么用", "如何使用", "坏了", "故障", "问题", "错误",
                "不能", "无法", "卡", "慢", "热", "连不上", "闪退",
                "打不开", "充电", "没声音", "设置", "连接", "配对"
            ],
            "negotiation": [
                "便宜", "优惠", "打折", "降价", "太贵", "能不能",
                "少点", "便宜点", "再便宜", "能不能便宜", "折扣",
                "减", "少", "底价", "最低"
            ],
            "greeting": ["你好", "您好", "hi", "hello", "在吗", "在不在", "嗨"],
            "farewell": ["再见", "拜拜", "bye", "谢谢", "感谢"]
        }

        # 优先检测问候和告别
        for intent in ["greeting", "farewell"]:
            if any(kw in query_lower for kw in INTENT_KEYWORDS.get(intent, [])):
                return intent, 0.85

        # 统计各意图匹配次数
        intent_scores = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            if intent in ["greeting", "farewell"]:
                continue
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                intent_scores[intent] = score

        # 检查历史上下文中的产品指代（如"第二款"、"那个"等）
        if not intent_scores and history:
            history_text = " ".join([h.get("content", "") for h in history[-3:]])
            # 如果历史中有产品推荐，当前询问是对产品的进一步了解
            if any(kw in history_text for kw in ["款", "推荐", "产品", "耳机", "手机", "电脑"]):
                if any(kw in query_lower for kw in ["详细介绍", "说说", "详情", "参数", "功能", "第二款", "第一款", "哪款", "这款", "那个", "呢"]):
                    logger.info(f"[SupervisorAgent] 检测到历史产品指代，分类为 sales")
                    return "sales", 0.6

        if not intent_scores:
            return "general", 0.4

        best_intent = max(intent_scores, key=intent_scores.get)
        confidence = min(0.4 + intent_scores[best_intent] * 0.1, 0.7)

        logger.info(f"[SupervisorAgent] 规则意图识别(兜底): {best_intent} (置信度: {confidence:.2f})")
        return best_intent, confidence

    # ============ 异步任务路由 ============

    async def route_task(
        self,
        intent: str,
        query: str,
        context: SessionContext
    ) -> List[Tuple[str, SkillResult]]:
        """
        异步任务路由 - 使用 asyncio.gather 并行执行多个 Skill

        Args:
            intent: 识别的意图
            query: 用户查询
            context: 会话上下文

        Returns:
            [(agent/skill名称, 执行结果), ...]
        """
        logger.info(f"[SupervisorAgent] route_task 意图: {intent}, query: {query}")

        # 1. 构建并行任务列表
        tasks = []
        task_names = []

        # 客户分类始终执行（并行）
        tasks.append(self._run_customer_classifier_async(query, context))
        task_names.append("customer_classifier")

        # 2. 根据意图添执行对应 Skill（并行）
        logger.info(f"[SupervisorAgent] 路由检查: intent={intent}")
        if intent == "sales":
            logger.info(f"[SupervisorAgent] 执行销售技能...")
            tasks.append(self._run_sales_agent_async(query, context))
            task_names.append("sales_agent")

        elif intent == "tech_support":
            tasks.append(self._run_tech_support_agent_async(query, context))
            task_names.append("tech_support_agent")

        elif intent == "negotiation":
            tasks.append(self._run_negotiation_skill_async(query, context))
            task_names.append("negotiation")

        elif intent == "greeting":
            # 问候不需要并行，直接同步返回
            return [("system", SkillResult(
                success=True,
                data={"message": "您好！有什么可以帮助您的吗？"},
                message="问候回复"
            ))]

        elif intent == "farewell":
            return [("system", SkillResult(
                success=True,
                data={"message": "再见！祝您生活愉快！"},
                message="告别回复"
            ))]

        else:  # general
            tasks.append(self._run_general_async(query, context))
            task_names.append("general")

        # 3. 使用 asyncio.gather 并行执行所有任务
        logger.info(f"[SupervisorAgent] 使用 asyncio.gather 并行执行 {len(tasks)} 个任务")
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 整理结果
        results = []
        for name, result in zip(task_names, task_results):
            if isinstance(result, Exception):
                logger.error(f"[SupervisorAgent] Task {name} 执行异常: {result}")
                results.append((name, None))
            elif result:
                logger.info(f"[SupervisorAgent] Task {name} 执行完成: success={result.success}")
                results.append((name, result))
            else:
                logger.warning(f"[SupervisorAgent] Task {name} 返回空结果")
                results.append((name, None))

        return results

    async def _run_customer_classifier_async(
        self,
        query: str,
        context: SessionContext
    ) -> Optional[SkillResult]:
        """异步运行客户分类 Skill"""
        try:
            skill_context = context.get_context_for_skill("customer_classifier")
            skill_context["query"] = query

            # 直接 await，不要用 asyncio.run()
            result = await self.skill_manager.registry.execute("customer_classifier", skill_context)

            if result.success:
                context.update_skill_context("customer_classifier", result.data)
                logger.info(f"[SupervisorAgent] 客户分类: {result.data.get('customer_type')}")

            return result
        except Exception as e:
            logger.error(f"[SupervisorAgent] 客户分类失败: {e}")
            return None

    async def _run_sales_agent_async(
        self,
        query: str,
        context: SessionContext
    ) -> Optional[SkillResult]:
        """异步运行销售 Agent"""
        try:
            skill_context = context.get_context_for_skill("sales_agent")
            skill_context["query"] = query

            # 传入对话历史，用于解析"第二款"等指代
            skill_context["history"] = [
                {"role": t.role, "content": t.content}
                for t in context.turn_history[-6:]
            ]

            result = await self.skill_manager.registry.execute("sales_agent", skill_context)

            if result.success:
                context.update_skill_context("sales_agent", result.data)
                logger.info(f"[SupervisorAgent] 销售处理完成: {result.message}")

            return result
        except Exception as e:
            logger.error(f"[SupervisorAgent] 销售处理失败: {e}")
            return None

    async def _run_tech_support_agent_async(
        self,
        query: str,
        context: SessionContext
    ) -> Optional[SkillResult]:
        """异步运行技术支持 Agent"""
        try:
            skill_context = context.get_context_for_skill("tech_support")
            skill_context["query"] = query

            result = await self.skill_manager.registry.execute("tech_support", skill_context)

            if result.success:
                context.update_skill_context("tech_support", result.data)
                logger.info(f"[SupervisorAgent] 技术支持完成: {result.message}")

            return result
        except Exception as e:
            logger.error(f"[SupervisorAgent] 技术支持处理失败: {e}")
            return None

    async def _run_negotiation_skill_async(
        self,
        query: str,
        context: SessionContext
    ) -> Optional[SkillResult]:
        """异步运行价格谈判 Skill"""
        try:
            skill_context = context.get_context_for_skill("negotiation")
            skill_context["query"] = query

            result = await self.skill_manager.registry.execute("negotiation", skill_context)

            if result.success:
                context.update_skill_context("negotiation", result.data)
                logger.info(f"[SupervisorAgent] 谈判处理完成: {result.message}")

            return result
        except Exception as e:
            logger.error(f"[SupervisorAgent] 谈判处理失败: {e}")
            return None

    async def _run_general_async(
        self,
        query: str,
        context: SessionContext
    ) -> Optional[SkillResult]:
        """异步通用查询处理"""
        try:
            prefetched = context.metadata.get("prefetched_rag_result") if context else None
            if isinstance(prefetched, dict) and prefetched.get("query") == query:
                rag_results = prefetched.get("documents", [])
            else:
                rag_results = await self._query_knowledge_base_async(query, context)
            if rag_results:
                rephrased_response = await self._format_rag_response(rag_results, query)
                return SkillResult(
                    success=True,
                    data={
                        "intent": "general",
                        "response": rephrased_response,
                        "sources": ["knowledge_base"]
                    },
                    message="知识库查询成功",
                    confidence=0.8
                )

            return SkillResult(
                success=False,
                error="未找到相关信息",
                confidence=0.0
            )
        except Exception as e:
            logger.error(f"[SupervisorAgent] 通用处理失败: {e}")
            return None

    async def _query_knowledge_base_async(self, query: str, context: SessionContext = None) -> List[Dict]:
        """异步查询知识库"""
        try:
            from tools.rag_tool import rag_tool

            chat_history = []
            if context and hasattr(context, 'turn_history'):
                chat_history = [
                    {"role": t.role, "content": t.content}
                    for t in context.turn_history[-6:]
                ]
                logger.info(f"[SupervisorAgent] RAG查询使用对话历史: {len(chat_history)} 条")

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: rag_tool.retrieve(
                    query=query,
                    top_k=3,
                    enable_self_rag=True,
                    llm=self._get_llm(),
                    use_hybrid=True,
                    chat_history=chat_history,
                    retrieval_policy=context.metadata.get("retrieval_policy") if context else None,
                    trace_id=context.metadata.get("trace_id") if context else None,
                )
            )

            if result.get("success") and result.get("documents"):
                user_role = (context.metadata.get("retrieval_policy") or {}).get("user_role") if context else None
                if user_role:
                    try:
                        from app.services.knowledge_admin_service import knowledge_admin_service

                        result["documents"] = knowledge_admin_service.filter_retrieved_documents_for_role(
                            result["documents"],
                            role=user_role,
                        )
                    except Exception as filter_error:
                        logger.warning(f"[SupervisorAgent] RAG权限过滤失败，已返回空结果: {filter_error}")
                        result["documents"] = []

                seen_contents = set()
                unique_docs = []
                for doc in result["documents"]:
                    content_hash = hash(doc.get("content", "")[:100])
                    if content_hash not in seen_contents:
                        seen_contents.add(content_hash)
                        unique_docs.append(doc)
                        if len(unique_docs) >= 3:
                            break
                logger.info(f"[SupervisorAgent] RAG检索: 原始{len(result['documents'])}条, 去重后{len(unique_docs)}条")
                return unique_docs

            return []
        except Exception as e:
            logger.error(f"[SupervisorAgent] 知识库查询失败: {e}")
            return []

    async def _format_rag_response(self, documents: List[Dict], query: str = "") -> str:
        """格式化 RAG 结果 - 使用 LLM 重新组织语言"""
        if not documents:
            return "抱歉，知识库中没有找到相关信息呢～"

        cleaned_contents = []
        for doc in documents:
            raw_content = doc.get("content", "")
            sanitized = self._sanitize_content(raw_content)
            cleaned_contents.append(sanitized)

        combined_text = "\n---\n".join(cleaned_contents)

        prompt = RAG_RESULT_REPHRASE_PROMPT.format(
            query=query or "一般查询",
            content=combined_text
        )

        try:
            llm = self._get_llm()
            async with _llm_rate_limiter:
                response = await llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"[SupervisorAgent] LLM润色RAG结果成功，长度: {len(content)}")
            return content
        except Exception as e:
            logger.error(f"[SupervisorAgent] LLM润色失败: {e}，使用备用回复")
            return f"好的，我帮您查了一下：\n\n{combined_text[:200]}..."

    async def _format_rag_response_stream(
        self, documents: List[Dict], query: str = ""
    ) -> AsyncGenerator[str, None]:
        """流式格式化 RAG 结果 - 逐 token 产出 LLM 输出。"""
        if not documents:
            yield "抱歉，知识库中没有找到相关信息呢～"
            return

        cleaned_contents = []
        for doc in documents:
            raw_content = doc.get("content", "")
            sanitized = self._sanitize_content(raw_content)
            cleaned_contents.append(sanitized)

        combined_text = "\n---\n".join(cleaned_contents)
        prompt = RAG_RESULT_REPHRASE_PROMPT.format(
            query=query or "一般查询",
            content=combined_text,
        )

        try:
            llm = self._get_streaming_llm()
            async with _llm_rate_limiter:
                async for chunk in llm.astream(prompt):
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if content:
                        yield content
        except Exception as e:
            logger.error(f"[SupervisorAgent] 流式LLM润色失败: {e}，使用备用回复")
            yield f"好的，我帮您查了一下：\n\n{combined_text[:200]}..."

    async def process_stream(
        self,
        query: str,
        context: SessionContext,
        trace_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式处理用户查询，逐步 yield 中间事件和 token。

        Yields:
            {"type": "intent", "intent": ..., "confidence": ...}
            {"type": "retrieved", "count": ...}
            {"type": "token", "content": "..."}
            {"type": "done"}
        """
        logger.info(f"[SupervisorAgent] 流式处理查询: {query[:50]}...")
        if trace_id:
            context.metadata["trace_id"] = trace_id

        # ---- Step 1: Intent classification ----
        intent, confidence = await self.classify_intent_llm(query, context.turn_history)
        yield {"type": "intent", "intent": intent, "confidence": confidence}
        logger.info(f"[SupervisorAgent] 流式意图: {intent} ({confidence:.2f})")

        # ---- Step 2: Retrieve + respond ----
        full_message = ""
        if intent == "general":
            # Reuse prefetched RAG results if available.
            prefetched = context.metadata.get("prefetched_rag_result")
            if prefetched and prefetched.get("query") == query:
                documents = prefetched.get("documents", [])
            else:
                documents = await self._query_knowledge_base_async(query, context)

            yield {"type": "retrieved", "count": len(documents)}

            if documents:
                async for token in self._format_rag_response_stream(documents, query):
                    full_message += token
                    yield {"type": "token", "content": token}
            else:
                fallback_msg = "抱歉，知识库中没有找到相关信息。"
                full_message = fallback_msg
                yield {"type": "token", "content": fallback_msg}
        else:
            # Non-general intents: run state graph (skills, etc.), then chunk result.
            graph = self._build_state_graph()
            graph_state = await graph.run(
                AgentGraphState(query=query, context=context, trace_id=trace_id)
            )
            final_response = graph_state.final_response
            if not final_response:
                final_response = {
                    "success": False,
                    "message": "抱歉，处理失败。",
                    "intent": intent,
                    "confidence": confidence,
                    "evaluation_score": 0.0,
                }
            full_message = final_response.get("message", "")
            yield {"type": "token", "content": full_message}

        # ---- Step 3: Record conversation ----
        context.add_turn(
            role="user",
            content=query,
            agent_name="supervisor",
            intent=intent,
            evaluation_score=0.0,
            trace_id=trace_id,
        )
        context.add_turn(
            role="assistant",
            content=full_message,
            agent_name="supervisor",
            intent=intent,
            evaluation_score=0.0,
            trace_id=trace_id,
        )

        yield {"type": "done"}

    def _sanitize_content(self, content: str) -> str:
        """清理内容，防止注入攻击"""
        import re

        content = content.strip()

        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<[^>]+>', '', content)

        content = content.replace("'", "\\'").replace('"', '\\"')
        content = content.replace(";", "；").replace("--", "——")
        content = content.replace("UNION", "联合").replace("SELECT", "查询").replace("DROP", "删除")
        content = content.replace("INSERT", "添加").replace("UPDATE", "更新").replace("DELETE", "删除")
        content = re.sub(r'https?://\S+', '[链接]', content)

        content = re.sub(r'\s+', ' ', content)

        if len(content) > 300:
            content = content[:300] + "..."

        return content

    # ============ 主处理流程 ============

    async def process(
        self,
        query: str,
        context: SessionContext,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        处理用户查询（异步主流程）

        Args:
            query: 用户查询
            context: 会话上下文

        Returns:
            处理结果
        """
        logger.info(f"[SupervisorAgent] 处理查询: {query[:50]}...")
        if trace_id:
            context.metadata["trace_id"] = trace_id

        graph = self._build_state_graph()
        graph_state = await graph.run(
            AgentGraphState(query=query, context=context, trace_id=trace_id)
        )
        final_response = graph_state.final_response
        final_response["agent_graph"] = {
            "definition": graph.definition(),
            "node_status": graph_state.node_status,
            "plan": graph_state.plan,
            "metadata": graph_state.metadata,
        }

        # 4. 记录对话
        context.add_turn(
            role="user",
            content=query,
            agent_name="supervisor",
            intent=graph_state.intent,
            rag_results=None,
            evaluation_score=final_response.get("evaluation_score", 0.0),
            trace_id=trace_id,
        )

        final_response["trace_id"] = trace_id or context.metadata.get("trace_id")
        return final_response

    async def _integrate_results_async(
        self,
        intent: str,
        routing_results: List[Tuple[str, SkillResult]],
        context: SessionContext,
        intent_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        异步整合各 Agent/Skill 的结果

        Args:
            intent: 意图类型
            routing_results: 路由结果列表
            context: 会话上下文

        Returns:
            整合后的响应
        """
        if not routing_results:
            logger.warning(f"[SupervisorAgent] routing_results 为空!")
            return {
                "success": False,
                "message": "抱歉，我暂时无法处理您的问题，请稍后重试。",
                "intent": intent,
                "evaluation_score": 0.0
            }

        logger.info(f"[SupervisorAgent] routing_results: {[(name, r.success if r else 'None') for name, r in routing_results]}")

        # 收集所有结果
        all_messages = []
        primary_result = None
        total_score = 0.0
        score_count = 0

        for name, result in routing_results:
            logger.info(f"[SupervisorAgent] 处理结果: name={name}, success={result.success if result else None}, data={result.data if result else None}")
            if result and result.success:
                if result.data:
                    if isinstance(result.data, dict):
                        msg = (
                            result.data.get("formatted_response") or
                            result.data.get("recommendation_response") or
                            result.data.get("negotiation_message") or
                            result.data.get("response") or
                            result.data.get("message")
                        )
                        if msg:
                            all_messages.append(f"[{name}]: {msg}")
                    elif isinstance(result.data, str):
                        all_messages.append(f"[{name}]: {result.data}")

                # 优先选择非 customer_classifier 的结果作为主结果
                if name != "customer_classifier" and primary_result is None:
                    primary_result = result

                if result.evaluation_score > 0:
                    total_score += result.evaluation_score
                    score_count += 1

        # 如果没有找到业务 skill 的结果，回退到第一个非 customer_classifier 的结果
        if primary_result is None:
            for name, result in routing_results:
                if name != "customer_classifier" and result and result.success:
                    primary_result = result
                    break

        # 构建最终回复
        logger.info(f"[SupervisorAgent] primary_result: {primary_result}")
        logger.info(f"[SupervisorAgent] primary_data: {primary_result.data if primary_result else None}")
        if primary_result:
            primary_data = primary_result.data
            if isinstance(primary_data, dict):
                final_message = (
                    primary_data.get("formatted_response") or
                    primary_data.get("recommendation_response") or
                    primary_data.get("negotiation_message") or
                    primary_data.get("response") or
                    primary_data.get("message") or
                    "处理完成"
                )
                logger.info(f"[SupervisorAgent] 提取的 final_message: {final_message[:100] if final_message else None}")
            else:
                final_message = str(primary_data)
        else:
            final_message = " ".join(all_messages) if all_messages else "抱歉，未能处理您的请求。"
            logger.info(f"[SupervisorAgent] all_messages: {all_messages}")

        # 计算平均评估分数
        avg_score = total_score / score_count if score_count > 0 else 0.5

        return {
            "success": True,
            "message": final_message,
            "intent": intent,
            "intent_confidence": intent_confidence,
            "customer_type": context.metadata.get("customer_type"),
            "skills_used": [name for name, _ in routing_results],
            "all_results": [
                {"agent": name, "success": r.success, "message": r.message}
                for name, r in routing_results if r
            ],
            "evaluation_score": avg_score,
            "session_summary": context.get_session_summary()
        }


# 全局实例（延迟初始化，避免循环导入）
_supervisor_agent_instance: Optional[SupervisorAgent] = None


def get_supervisor_agent() -> SupervisorAgent:
    """获取 SupervisorAgent 全局实例"""
    global _supervisor_agent_instance
    if _supervisor_agent_instance is None:
        _supervisor_agent_instance = SupervisorAgent()
    return _supervisor_agent_instance
