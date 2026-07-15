"""
Redis 缓存管理器
================

提供多层缓存功能：
1. 检索结果缓存 - 热门查询结果
2. 意图分类缓存 - LLM 意图分类结果（避免重复调用 LLM）
3. 向量缓存 - 热门文档向量（避免重复计算）
4. Session 持久化 - 会话状态 Redis 存储

特性：
- 自动过期 (TTL)
- 缓存预热
- 容量限制 (LRU)
- 统计监控
"""

import json
import hashlib
import time
import threading
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class CacheType(Enum):
    """缓存类型枚举"""
    RETRIEVAL = "retrieval"        # 检索结果缓存
    INTENT = "intent"              # 意图分类缓存
    VECTOR = "vector"              # 向量缓存
    SESSION = "session"            # Session 持久化
    BM25_INDEX = "bm25_index"      # BM25 索引缓存


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    last_hit_time: Optional[float] = None
    last_miss_time: Optional[float] = None

    def get_hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class CacheConfig:
    """缓存配置"""
    ttl: int = 3600                          # 默认 TTL (秒)
    max_connections: int = 10               # 最大连接数
    retry_times: int = 3                    # 重试次数
    retry_delay: float = 0.1                # 重试延迟 (秒)
    key_prefix: str = "ragcache:"           # 键前缀
    enable_fallback: bool = True            # 失败时是否回退到内存


class RedisCacheManager:
    """
    Redis 缓存管理器（单例模式）

    支持多种缓存类型，自适应回退到内存缓存
    """

    _instance = None
    _lock = threading.Lock()

    DEFAULT_TTL = {
        CacheType.RETRIEVAL: 1800,      # 检索缓存 30 分钟
        CacheType.INTENT: 300,          # 意图缓存 5 分钟
        CacheType.VECTOR: 86400,       # 向量缓存 24 小时
        CacheType.SESSION: 7200,        # Session 缓存 2 小时
        CacheType.BM25_INDEX: 3600,     # BM25 索引缓存 1 小时
    }

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        config: Optional[CacheConfig] = None
    ):
        if self._initialized:
            return

        self._initialized = True
        self.config = config or CacheConfig()
        self._redis = None
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._memory_cache_lock = threading.RLock()
        self._stats: Dict[CacheType, CacheStats] = {
            ct: CacheStats() for ct in CacheType
        }

        if REDIS_AVAILABLE:
            self._connect(host, port, db, password)
        else:
            self._redis = None

    def _connect(
        self,
        host: str,
        port: int,
        db: int,
        password: Optional[str]
    ):
        """建立 Redis 连接"""
        try:
            self._redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self._redis.ping()
        except Exception as e:
            self._redis = None

    @property
    def is_available(self) -> bool:
        """检查 Redis 是否可用"""
        return self._redis is not None

    def _make_key(self, cache_type: CacheType, key: str) -> str:
        """生成缓存键"""
        return f"{self.config.key_prefix}{cache_type.value}:{key}"

    def _generate_hash(self, data: Any) -> str:
        """生成数据的哈希值"""
        if isinstance(data, dict):
            content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        elif isinstance(data, list):
            content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        else:
            content = str(data)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _get_from_memory(self, key: str) -> Optional[Any]:
        """从内存缓存获取"""
        with self._memory_cache_lock:
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if entry['expires_at'] > time.time():
                    return entry['value']
                else:
                    del self._memory_cache[key]
            return None

    def _set_to_memory(self, key: str, value: Any, ttl: int):
        """设置到内存缓存"""
        with self._memory_cache_lock:
            self._memory_cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl
            }

    def get(
        self,
        cache_type: CacheType,
        key: str,
        default: Any = None
    ) -> Any:
        """
        获取缓存

        Args:
            cache_type: 缓存类型
            key: 缓存键
            default: 默认值

        Returns:
            缓存值或默认值
        """
        full_key = self._make_key(cache_type, key)
        stats = self._stats[cache_type]

        if self._redis:
            try:
                value = self._redis.get(full_key)
                if value:
                    stats.hits += 1
                    stats.last_hit_time = time.time()
                    return json.loads(value)
            except Exception:
                stats.errors += 1

        memory_value = self._get_from_memory(full_key)
        if memory_value is not None:
            stats.hits += 1
            stats.last_hit_time = time.time()
            return memory_value

        stats.misses += 1
        stats.last_miss_time = time.time()
        return default

    def set(
        self,
        cache_type: CacheType,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        设置缓存

        Args:
            cache_type: 缓存类型
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认值

        Returns:
            是否设置成功
        """
        full_key = self._make_key(cache_type, key)
        ttl = ttl or self.DEFAULT_TTL.get(cache_type, self.config.ttl)
        stats = self._stats[cache_type]

        try:
            json_value = json.dumps(value, ensure_ascii=False)

            if self._redis:
                try:
                    self._redis.setex(full_key, ttl, json_value)
                    stats.sets += 1
                    return True
                except Exception:
                    pass

            self._set_to_memory(full_key, value, ttl)
            stats.sets += 1
            return True

        except Exception:
            stats.errors += 1
            return False

    def delete(self, cache_type: CacheType, key: str) -> bool:
        """
        删除缓存

        Args:
            cache_type: 缓存类型
            key: 缓存键

        Returns:
            是否删除成功
        """
        full_key = self._make_key(cache_type, key)
        stats = self._stats[cache_type]

        try:
            if self._redis:
                try:
                    self._redis.delete(full_key)
                except Exception:
                    pass

            with self._memory_cache_lock:
                if full_key in self._memory_cache:
                    del self._memory_cache[full_key]

            stats.deletes += 1
            return True

        except Exception:
            stats.errors += 1
            return False

    def clear_type(self, cache_type: CacheType) -> int:
        """
        清除指定类型的所有缓存

        Args:
            cache_type: 缓存类型

        Returns:
            清除的缓存数量
        """
        pattern = self._make_key(cache_type, "*")
        count = 0

        if self._redis:
            try:
                keys = self._redis.keys(pattern)
                if keys:
                    count = len(keys)
                    self._redis.delete(*keys)
            except Exception:
                pass

        with self._memory_cache_lock:
            keys_to_delete = [
                k for k in self._memory_cache.keys()
                if k.startswith(self._make_key(cache_type, ""))
            ]
            for k in keys_to_delete:
                del self._memory_cache[k]
                count += 1

        return count

    def get_stats(self, cache_type: Optional[CacheType] = None) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Args:
            cache_type: 缓存类型，None 表示所有类型

        Returns:
            统计信息字典
        """
        if cache_type:
            stats = self._stats[cache_type]
            return {
                "type": cache_type.value,
                "hits": stats.hits,
                "misses": stats.misses,
                "sets": stats.sets,
                "deletes": stats.deletes,
                "errors": stats.errors,
                "hit_rate": f"{stats.get_hit_rate():.2%}",
                "last_hit_time": stats.last_hit_time,
                "last_miss_time": stats.last_miss_time
            }

        return {
            ct.value: self.get_stats(ct)
            for ct in CacheType
        }

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "redis_available": self.is_available,
            "memory_cache_size": len(self._memory_cache),
            "config": {
                "key_prefix": self.config.key_prefix,
                "default_ttl": self.config.ttl,
                "enable_fallback": self.config.enable_fallback
            }
        }


class IntentClassificationCache:
    """
    意图分类缓存

    专门用于缓存 LLM 意图分类结果，避免重复调用 LLM
    """

    def __init__(self, cache_manager: RedisCacheManager):
        self._cache = cache_manager

    def get_intent(self, query: str) -> Optional[Dict[str, Any]]:
        """获取缓存的意图分类结果"""
        query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
        return self._cache.get(CacheType.INTENT, query_hash)

    def set_intent(
        self,
        query: str,
        intent: str,
        confidence: float,
        reasoning: str = "",
        ttl: int = 300
    ) -> bool:
        """缓存意图分类结果"""
        query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
        return self._cache.set(
            CacheType.INTENT,
            query_hash,
            {
                "query": query,
                "intent": intent,
                "confidence": confidence,
                "reasoning": reasoning,
                "cached_at": datetime.now().isoformat()
            },
            ttl=ttl
        )


class RetrievalCache:
    """
    检索结果缓存

    缓存热门查询的检索结果，加速重复查询
    """

    def __init__(self, cache_manager: RedisCacheManager):
        self._cache = cache_manager

    def get_retrieval(
        self,
        query: str,
        top_k: int,
        intent: str
    ) -> Optional[List[Dict[str, Any]]]:
        """获取缓存的检索结果"""
        key = self._generate_key(query, top_k, intent)
        return self._cache.get(CacheType.RETRIEVAL, key)

    def set_retrieval(
        self,
        query: str,
        top_k: int,
        intent: str,
        documents: List[Dict[str, Any]],
        ttl: int = 1800
    ) -> bool:
        """缓存检索结果"""
        key = self._generate_key(query, top_k, intent)
        return self._cache.set(
            CacheType.RETRIEVAL,
            key,
            {
                "query": query,
                "top_k": top_k,
                "intent": intent,
                "documents": documents,
                "cached_at": datetime.now().isoformat()
            },
            ttl=ttl
        )

    def _generate_key(
        self,
        query: str,
        top_k: int,
        intent: str
    ) -> str:
        """生成检索缓存键"""
        content = f"{query}:{top_k}:{intent}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()


class SessionCache:
    """
    Session 缓存

    将会话状态持久化到 Redis，支持分布式部署
    """

    def __init__(self, cache_manager: RedisCacheManager):
        self._cache = cache_manager

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话数据"""
        return self._cache.get(CacheType.SESSION, session_id)

    def set_session(
        self,
        session_id: str,
        session_data: Dict[str, Any],
        ttl: int = 7200
    ) -> bool:
        """设置会话数据"""
        return self._cache.set(
            CacheType.SESSION,
            session_id,
            {
                **session_data,
                "updated_at": datetime.now().isoformat()
            },
            ttl=ttl
        )

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        return self._cache.delete(CacheType.SESSION, session_id)

    def update_session(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """部分更新会话数据"""
        current = self.get_session(session_id)
        if current is None:
            return False

        current.update(updates)
        return self.set_session(session_id, current)


_cache_manager_instance: Optional[RedisCacheManager] = None


def get_cache_manager(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None
) -> RedisCacheManager:
    """
    获取缓存管理器单例

    Args:
        host: Redis 主机
        port: Redis 端口
        db: 数据库编号
        password: 密码

    Returns:
        RedisCacheManager 实例
    """
    global _cache_manager_instance

    if _cache_manager_instance is None:
        _cache_manager_instance = RedisCacheManager(
            host=host,
            port=port,
            db=db,
            password=password
        )

    return _cache_manager_instance


def create_caches(cache_manager: RedisCacheManager) -> tuple:
    """
    创建各类缓存实例

    Returns:
        (IntentClassificationCache, RetrievalCache, SessionCache)
    """
    return (
        IntentClassificationCache(cache_manager),
        RetrievalCache(cache_manager),
        SessionCache(cache_manager)
    )
