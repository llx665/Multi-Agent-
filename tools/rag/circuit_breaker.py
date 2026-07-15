"""
熔断器（Circuit Breaker）模块

保护外部依赖（Redis、ChromaDB、LLM API）免受级联故障影响。

状态机：
  closed (正常) → open (熔断) → half-open (半开) → closed (恢复)
                    ↑________________________|
"""

import time
from enum import Enum
from typing import Any, Callable, Optional


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreakerOpenError(Exception):
    """熔断器打开时抛出的异常"""
    pass


class CircuitBreaker:
    """熔断器

    Args:
        failure_threshold: 连续失败次数阈值，超过后熔断
        recovery_timeout: 熔断持续时间（秒），之后进入半开状态
        half_open_max_requests: 半开状态下允许的最大探测请求数
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self._half_open_used = 0

    def _reset(self):
        self.failure_count = 0
        self.success_count = 0
        self._half_open_used = 0

    def __call__(self, fn: Callable, *args, **kwargs) -> Any:
        """同步调用，受熔断器保护。"""
        self._check_state()
        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    async def acall(self, fn: Callable, *args, **kwargs) -> Any:
        """异步调用，受熔断器保护。"""
        self._check_state()
        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _check_state(self):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._half_open_used = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN "
                    f"(failure_threshold={self.failure_threshold}, "
                    f"retry_after={self.recovery_timeout - (time.time() - self.last_failure_time):.1f}s)"
                )

        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_used >= self.half_open_max_requests:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is HALF_OPEN "
                    f"and has used all {self.half_open_max_requests} probe requests"
                )
            self._half_open_used += 1

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._reset()
        self.failure_count = 0

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._reset()


# 预定义的熔断器实例
redis_circuit_breaker = CircuitBreaker(
    name="redis",
    failure_threshold=3,
    recovery_timeout=30.0,
)

chroma_circuit_breaker = CircuitBreaker(
    name="chromadb",
    failure_threshold=5,
    recovery_timeout=60.0,
)

llm_circuit_breaker = CircuitBreaker(
    name="llm_api",
    failure_threshold=10,
    recovery_timeout=30.0,
    half_open_max_requests=2,
)
