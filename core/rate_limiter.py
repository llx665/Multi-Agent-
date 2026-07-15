"""
限流器模块

提供资源级别的并发控制和速率限制，保护 LLM API、Embedding 模型等
关键资源不被突发流量打垮。
"""

import asyncio
import time
from typing import Dict, List, Optional


class AsyncRateLimiter:
    """基于令牌桶的异步速率限制器

    限制操作在给定时间窗口内的执行次数。
    例如: 每分钟最多 30 次 LLM 调用。

    Args:
        max_calls: 时间窗口内最大调用次数
        window: 时间窗口大小（秒）
    """

    def __init__(self, max_calls: int = 60, window: float = 60.0):
        self.max_calls = max_calls
        self.window = window
        self._call_timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """尝试获取许可，返回等待时间（秒）。"""
        async with self._lock:
            now = time.time()
            cutoff = now - self.window

            # 清理过期时间戳
            self._call_timestamps = [t for t in self._call_timestamps if t > cutoff]

            if len(self._call_timestamps) >= self.max_calls:
                # 需要等待最早的时间戳过期
                wait = self._call_timestamps[0] + self.window - now
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.time()

            self._call_timestamps.append(now)
            return now

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass


class ResourcePool:
    """资源池，限制最大并发数

    可选的排队机制，防止并发数超过资源容量。

    Args:
        max_concurrent: 最大并发数
        queue_size: 排队队列大小（0 = 不排队，直接拒绝）
    """

    def __init__(self, name: str = "default", max_concurrent: int = 5, queue_size: int = 0):
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size) if queue_size > 0 else None
        self._waiting = 0

    async def acquire(self) -> bool:
        """尝试获取资源。返回是否获取成功。

        如果设置了 queue_size 且队列已满，立即返回 False。
        """
        if self._queue is not None:
            try:
                self._queue.put_nowait(object())
                self._waiting += 1
            except asyncio.QueueFull:
                return False

        await self._semaphore.acquire()

        if self._queue is not None:
            await self._queue.get()
            self._waiting -= 1

        return True

    def release(self):
        self._semaphore.release()

    @property
    def waiting(self) -> int:
        return self._waiting

    async def __aenter__(self):
        ok = await self.acquire()
        if not ok:
            raise RuntimeError(
                f"ResourcePool '{self.name}' queue is full. "
                f"max_concurrent={self._semaphore._value + sum(1 for _ in []) if hasattr(self._semaphore, '_value') else 'unknown'}"
            )
        return self

    async def __aexit__(self, *args):
        self.release()


class LLMRateLimiter:
    """LLM 调用限流器（并发 + 速率 双重限制）

    组合了：
    1. 最大并发数（防止同时 N 个 LLM 调用淹没有限的连接池）
    2. 速率限制（每分钟 M 次调用）

    Args:
        max_concurrent: 同时进行的最大 LLM 调用数
        requests_per_minute: 每分钟允许的最大调用数
    """

    def __init__(self, max_concurrent: int = 5, requests_per_minute: int = 30):
        self.pool = ResourcePool(
            name="llm",
            max_concurrent=max_concurrent,
        )
        self.rate_limiter = AsyncRateLimiter(
            max_calls=requests_per_minute,
            window=60.0,
        )

    async def acquire(self):
        await self.pool.acquire()
        await self.rate_limiter.acquire()

    def release(self):
        self.pool.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        self.release()


# 全局实例
llm_rate_limiter = LLMRateLimiter(max_concurrent=5, requests_per_minute=30)
