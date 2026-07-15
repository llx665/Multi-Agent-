import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.session_context import SessionContext
from skills.base import SkillResult


@pytest.mark.asyncio
async def test_state_graph_executor_retries_timeout_and_uses_fallback():
    from agents.agent_state_graph import AgentGraphState, NodeExecutionPolicy, StateGraphExecutor

    attempts = {"count": 0}

    async def slow_node(state):
        attempts["count"] += 1
        await asyncio.sleep(0.05)
        return state

    async def fallback_node(state, error):
        state.metadata["fallback_error"] = type(error).__name__
        return state

    graph = StateGraphExecutor()
    graph.add_node(
        "slow",
        slow_node,
        policy=NodeExecutionPolicy(timeout_seconds=0.01, retries=1, fallback=fallback_node),
    )

    result = await graph.run(AgentGraphState(query="hello"))

    assert attempts["count"] == 2
    assert result.metadata["fallback_error"] == "TimeoutError"
    assert result.node_status["slow"]["status"] == "fallback"
    assert result.node_status["slow"]["attempts"] == 2


@pytest.mark.asyncio
async def test_state_graph_executor_records_node_timing_and_error_history():
    from agents.agent_state_graph import AgentGraphState, NodeExecutionPolicy, StateGraphExecutor

    attempts = {"count": 0}

    async def flaky_node(state):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("first failure")
        return state

    graph = StateGraphExecutor()
    graph.add_node("flaky", flaky_node, policy=NodeExecutionPolicy(timeout_seconds=1, retries=1))

    result = await graph.run(AgentGraphState(query="hello"))
    status = result.node_status["flaky"]

    assert status["status"] == "success"
    assert status["attempts"] == 2
    assert status["started_at"]
    assert status["ended_at"]
    assert status["duration_ms"] >= 0
    assert status["errors"] == [{"attempt": 1, "type": "ValueError", "message": "first failure"}]


@pytest.mark.asyncio
async def test_supervisor_process_exposes_explicit_state_graph(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules,
        "core.agent_factory",
        SimpleNamespace(agent_factory=SimpleNamespace(get_llm=lambda: None)),
    )
    from agents.supervisor_agent import SupervisorAgent

    agent = SupervisorAgent()
    execution_order = []

    async def classify(query, history):
        execution_order.append("intent")
        return "general", 0.88

    async def route(intent, query, context):
        execution_order.append("execute")
        return [
            (
                "general",
                SkillResult(
                    success=True,
                    data={"response": "answer"},
                    message="ok",
                    confidence=0.8,
                ),
            )
        ]

    async def retrieve(query, context):
        return [{"content": "state graph doc", "metadata": {"source": "doc.md"}}]

    async def integrate(intent, routing_results, context, intent_confidence=0.5):
        execution_order.append("final")
        return {
            "success": True,
            "message": "answer",
            "intent": intent,
            "intent_confidence": intent_confidence,
            "evaluation_score": 0.8,
        }

    monkeypatch.setattr(agent, "classify_intent_llm", classify)
    monkeypatch.setattr(agent, "route_task", route)
    monkeypatch.setattr(agent, "_query_knowledge_base_async", retrieve)
    monkeypatch.setattr(agent, "_integrate_results_async", integrate)

    context = SessionContext(session_id="p1-state-graph-session", user_id="p1-state-graph-user")
    result = await agent.process("hello", context, trace_id="trace-p1")

    assert execution_order == ["intent", "execute", "final"]
    assert result["agent_graph"]["definition"] == [
        "intent",
        "plan",
        "retrieve",
        "execute",
        "verify",
        "replan",
        "final",
    ]
    assert result["agent_graph"]["node_status"]["intent"]["status"] == "success"
    assert result["agent_graph"]["node_status"]["execute"]["status"] == "success"
    assert result["agent_graph"]["node_status"]["final"]["status"] == "success"


@pytest.mark.asyncio
async def test_supervisor_retrieve_node_prefetches_rag_and_execute_reuses_it(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules,
        "core.agent_factory",
        SimpleNamespace(agent_factory=SimpleNamespace(get_llm=lambda: None)),
    )
    from agents.supervisor_agent import SupervisorAgent

    agent = SupervisorAgent()
    calls = {"rag": 0}

    async def classify(query, history):
        return "general", 0.9

    async def customer_classifier(query, context):
        return SkillResult(success=True, data={"customer_type": "normal"}, message="ok")

    async def retrieve(query, context):
        calls["rag"] += 1
        return [{"content": "prefetched knowledge", "metadata": {"source": "doc.md"}}]

    async def format_response(documents, query=""):
        return f"formatted:{documents[0]['content']}"

    monkeypatch.setattr(agent, "classify_intent_llm", classify)
    monkeypatch.setattr(agent, "_run_customer_classifier_async", customer_classifier)
    monkeypatch.setattr(agent, "_query_knowledge_base_async", retrieve)
    monkeypatch.setattr(agent, "_format_rag_response", format_response)

    context = SessionContext(
        session_id=f"p1-prefetch-session-{uuid4().hex}",
        user_id=f"p1-prefetch-user-{uuid4().hex}",
    )

    result = await agent.process("知识库问题", context, trace_id="trace-prefetch")

    assert calls["rag"] == 1
    assert result["message"] == "formatted:prefetched knowledge"
    assert result["agent_graph"]["metadata"]["retrieval"]["document_count"] == 1
    assert result["agent_graph"]["metadata"]["retrieval"]["source"] == "state_graph"
    assert context.metadata["prefetched_rag_result"]["documents"][0]["content"] == "prefetched knowledge"


@pytest.mark.asyncio
async def test_supervisor_low_quality_retrieve_sets_replan_metadata(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules,
        "core.agent_factory",
        SimpleNamespace(agent_factory=SimpleNamespace(get_llm=lambda: None)),
    )
    from agents.supervisor_agent import SupervisorAgent

    agent = SupervisorAgent()

    async def classify(query, history):
        return "general", 0.9

    async def customer_classifier(query, context):
        return SkillResult(success=True, data={"customer_type": "normal"}, message="ok")

    async def retrieve(query, context):
        return []

    monkeypatch.setattr(agent, "classify_intent_llm", classify)
    monkeypatch.setattr(agent, "_run_customer_classifier_async", customer_classifier)
    monkeypatch.setattr(agent, "_query_knowledge_base_async", retrieve)

    context = SessionContext(
        session_id=f"p1-low-quality-session-{uuid4().hex}",
        user_id=f"p1-low-quality-user-{uuid4().hex}",
    )

    result = await agent.process("没有命中的问题", context, trace_id="trace-low-quality")

    graph_meta = result["agent_graph"]["metadata"]
    assert graph_meta["retrieval"]["document_count"] == 0
    assert graph_meta["rag_fallback"]["needed"] is True
    assert graph_meta["verification"]["needs_replan"] is True
    assert graph_meta["replanned"]["strategy"] == "clarification"
    assert graph_meta["replanned"]["document_count"] == 0
    assert result["skills_used"] == ["fallback"]


@pytest.mark.asyncio
async def test_supervisor_replan_retries_with_rewritten_query(monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules,
        "core.agent_factory",
        SimpleNamespace(agent_factory=SimpleNamespace(get_llm=lambda: None)),
    )
    from agents.supervisor_agent import SupervisorAgent

    agent = SupervisorAgent()
    queries = []

    async def classify(query, history):
        return "general", 0.9

    async def customer_classifier(query, context):
        return SkillResult(success=True, data={"customer_type": "normal"}, message="ok")

    async def retrieve(query, context):
        queries.append(query)
        if len(queries) == 1:
            return []
        return [{"content": "rewritten knowledge", "metadata": {"source": "rewrite.md"}}]

    async def format_response(documents, query=""):
        return f"formatted:{documents[0]['content']}:{query}"

    monkeypatch.setattr(agent, "classify_intent_llm", classify)
    monkeypatch.setattr(agent, "_run_customer_classifier_async", customer_classifier)
    monkeypatch.setattr(agent, "_query_knowledge_base_async", retrieve)
    monkeypatch.setattr(agent, "_format_rag_response", format_response)

    context = SessionContext(
        session_id=f"p1-rewrite-session-{uuid4().hex}",
        user_id=f"p1-rewrite-user-{uuid4().hex}",
    )

    result = await agent.process("manual missing", context, trace_id="trace-rewrite")

    graph_meta = result["agent_graph"]["metadata"]
    assert len(queries) == 2
    assert queries[1] == graph_meta["rag_fallback"]["rewrite_query"]
    assert graph_meta["replanned"]["strategy"] == "rewrite_retry"
    assert graph_meta["replanned"]["document_count"] == 1
    assert result["message"] == f"formatted:rewritten knowledge:{queries[1]}"
    assert "general_replan" in result["skills_used"]


def test_low_quality_rag_fallback_plans_query_rewrite_and_clarification():
    from tools.rag.fallback_policy import plan_low_quality_rag_fallback

    decision = plan_low_quality_rag_fallback(
        query="怎么处理一个没有说明书的异常报错？",
        retrieval_result={"success": True, "documents": [], "has_relevant_info": False},
        quality="none",
    )

    assert decision["needed"] is True
    assert decision["strategy"] == "clarify_and_rewrite"
    assert decision["rewrite_query"]
    assert decision["clarification_message"]
    assert decision["retry_options"]["top_k"] > 3


def test_chat_response_exposes_rag_fallback_metadata():
    from backend.app.schemas import ChatResponse

    response = ChatResponse(
        session_id="s1",
        trace_id="t1",
        message="m",
        rag_fallback={"needed": True, "strategy": "clarify_and_rewrite"},
    )

    assert response.rag_fallback["needed"] is True
    assert response.rag_fallback["strategy"] == "clarify_and_rewrite"


def test_long_term_memory_tracks_importance_ttl_and_consent():
    from tools.rag.context_engineering import LongTermMemoryManager

    storage_path = Path(".pytest_cache") / f"p1-long-term-memory-{uuid4().hex}"
    storage_path.mkdir(parents=True, exist_ok=True)
    manager = LongTermMemoryManager(storage_path=str(storage_path))
    manager.update_preference(
        "p1-user",
        "preferred_brand",
        "Acme",
        source="explicit_user",
        confidence=0.9,
        importance=0.8,
        ttl_seconds=3600,
        consent=True,
    )

    profile = manager.get_or_create_profile("p1-user")
    meta = profile.preference_meta["preferred_brand"]

    assert meta["importance"] == 0.8
    assert meta["consent"] is True
    assert meta["ttl_seconds"] == 3600
    assert meta["expires_at"]

    manager.update_preference(
        "p1-user",
        "phone_number",
        "13800138000",
        source="explicit_user",
        consent=False,
    )

    assert "phone_number" not in profile.preferences
    assert profile.preference_history[-1]["skipped_reason"] == "missing_consent"
