"""Lightweight DAG-based state graph for Agent orchestration.

Supports parallel node execution based on explicit dependency declarations.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple


@dataclass
class AgentGraphState:
    query: str
    context: Any = None
    trace_id: Optional[str] = None
    intent: Optional[str] = None
    confidence: float = 0.0
    plan: Dict[str, Any] = field(default_factory=dict)
    retrieval_result: Dict[str, Any] = field(default_factory=dict)
    rag_fallback: Dict[str, Any] = field(default_factory=dict)
    routing_results: List[Tuple[str, Any]] = field(default_factory=list)
    final_response: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    node_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    needs_replan: bool = False


NodeHandler = Callable[[AgentGraphState], Awaitable[AgentGraphState]]
FallbackHandler = Callable[[AgentGraphState, Exception], Awaitable[AgentGraphState]]


@dataclass
class NodeExecutionPolicy:
    timeout_seconds: Optional[float] = 20.0
    retries: int = 0
    fallback: Optional[FallbackHandler] = None


@dataclass
class _NodeDef:
    handler: NodeHandler
    policy: NodeExecutionPolicy
    depends_on: Set[str] = field(default_factory=set)


class StateGraphExecutor:
    """Execute named async nodes respecting DAG dependencies.

    Nodes with all dependencies satisfied run in parallel via asyncio.gather,
    which can significantly reduce total wall-clock time when branches of the
    graph are independent (e.g. intent classification and retrieval).
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, _NodeDef] = {}

    def add_node(
        self,
        name: str,
        handler: NodeHandler,
        policy: Optional[NodeExecutionPolicy] = None,
        depends_on: Optional[Set[str]] = None,
    ) -> None:
        """Register a node with optional dependency declaration."""
        self._nodes[name] = _NodeDef(
            handler=handler,
            policy=policy or NodeExecutionPolicy(),
            depends_on=depends_on or set(),
        )

    def definition(self) -> List[str]:
        return list(self._nodes.keys())

    def _check_deadlock(self, completed: Set[str]) -> None:
        pending = set(self._nodes.keys()) - completed
        if not pending:
            return
        reachable = set()
        for name in pending:
            for dep in self._nodes[name].depends_on:
                if dep not in completed:
                    reachable.add(dep)
        # If every pending node depends on something still pending, we're stuck.
        if reachable and reachable.issubset(pending):
            raise RuntimeError(
                f"Graph deadlock: nodes {pending} depend on "
                f"uncompleted nodes {reachable}"
            )

    def _parallel_layers(self) -> List[List[str]]:
        """Compute topological layers for logging / debugging."""
        completed: Set[str] = set()
        layers: List[List[str]] = []
        while len(completed) < len(self._nodes):
            layer = [
                name for name in self._nodes
                if name not in completed
                and self._nodes[name].depends_on.issubset(completed)
            ]
            if not layer:
                break
            layers.append(layer)
            completed.update(layer)
        return layers

    async def run(self, state: AgentGraphState) -> AgentGraphState:
        """Execute the graph, running independent nodes concurrently."""
        completed: Set[str] = set()

        logger = _get_logger()
        layers = self._parallel_layers()
        logger.info(
            f"[StateGraph] parallel layers: "
            f"{' → '.join('+'.join(l) for l in layers)}"
        )

        while len(completed) < len(self._nodes):
            # Find all nodes whose dependencies are fully satisfied.
            ready = [
                name for name in self._nodes
                if name not in completed
                and self._nodes[name].depends_on.issubset(completed)
            ]

            if not ready:
                self._check_deadlock(completed)
                break

            # Run all ready nodes in parallel.
            tasks = {
                name: self._run_node(
                    name,
                    self._nodes[name].handler,
                    self._nodes[name].policy,
                    state,
                )
                for name in ready
            }

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            for name, result in zip(ready, results):
                if isinstance(result, Exception):
                    logger.error(
                        f"[StateGraph] node '{name}' failed: {result}"
                    )
                    raise result
                state = result
                completed.add(name)

        return state

    async def _run_node(
        self,
        name: str,
        handler: NodeHandler,
        policy: NodeExecutionPolicy,
        state: AgentGraphState,
    ) -> AgentGraphState:
        attempts = 0
        last_error: Optional[Exception] = None
        started_at = datetime.now().isoformat()
        started_perf = perf_counter()
        errors: List[Dict[str, Any]] = []

        for _ in range(policy.retries + 1):
            attempts += 1
            try:
                if policy.timeout_seconds is None:
                    state = await handler(state)
                else:
                    state = await asyncio.wait_for(handler(state), timeout=policy.timeout_seconds)
                state.node_status[name] = self._build_status(
                    status="success",
                    attempts=attempts,
                    started_at=started_at,
                    started_perf=started_perf,
                    errors=errors,
                )
                return state
            except Exception as error:
                last_error = error
                errors.append(
                    {
                        "attempt": attempts,
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                )

        if policy.fallback and last_error is not None:
            state = await policy.fallback(state, last_error)
            state.node_status[name] = self._build_status(
                status="fallback",
                attempts=attempts,
                started_at=started_at,
                started_perf=started_perf,
                errors=errors,
                error=type(last_error).__name__,
            )
            return state

        if last_error is not None:
            state.node_status[name] = self._build_status(
                status="failed",
                attempts=attempts,
                started_at=started_at,
                started_perf=started_perf,
                errors=errors,
                error=type(last_error).__name__,
            )
            raise last_error

        return state

    def _build_status(
        self,
        *,
        status: str,
        attempts: int,
        started_at: str,
        started_perf: float,
        errors: List[Dict[str, Any]],
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        ended_at = datetime.now().isoformat()
        node_status: Dict[str, Any] = {
            "status": status,
            "attempts": attempts,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": round((perf_counter() - started_perf) * 1000, 3),
            "errors": errors,
        }
        if error:
            node_status["error"] = error
        return node_status


def _get_logger():
    """Lazy logger to avoid import-time side effects."""
    from core.logger import LoggerManager
    return LoggerManager.get_logger("state_graph")
