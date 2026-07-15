"""
上下文工程实现 - Claude Code & Manus 最佳实践

三层记忆架构：
1. 短期记忆 (Short-term Memory) - 当前对话
2. 中期记忆 (Medium-term Memory) - 智能压缩
3. 长期记忆 (Long-term Memory) - 用户偏好/项目知识

核心功能：
- Offload: 信息卸载到外部存储
- Retrieve: 动态检索相关信息
- Compress: 智能压缩上下文
- Isolate: 分而治之，SubAgent 处理子任务

参考：
- Claude Code: 三层记忆架构，92%阈值触发压缩，8段式结构化存储
- Manus: KV缓存优化，工具遮蔽，文件系统作为上下文
"""

import threading
import json
import os
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import tiktoken

from core.logger import LoggerManager

logger = LoggerManager.get_logger("context_engineering")


class MemoryTier(Enum):
    """记忆层级"""
    SHORT_TERM = "short_term"      # 当前对话（实时访问）
    MEDIUM_TERM = "medium_term"    # 智能压缩（临时持久化）
    LONG_TERM = "long_term"        # 长期记忆（跨会话）


class CompressionStrategy(Enum):
    """压缩策略"""
    SEMANTIC_SUMMARY = "semantic_summary"      # 语义摘要
    STRUCTURED_EXTRACTION = "structured"       # 结构化提取
    KEY_POINTS = "key_points"                  # 关键点提取
    ENTITY_TRACKING = "entity_tracking"        # 实体跟踪


@dataclass
class MemoryEntry:
    """记忆条目"""
    content: str
    tier: MemoryTier
    timestamp: str
    embedding: Optional[List[float]] = None
    importance_score: float = 1.0
    entity_tags: List[str] = field(default_factory=list)
    source_turn: Optional[int] = None
    compressed_from: Optional[str] = None  # 如果是压缩后的，原始层级


@dataclass
class ConversationTurn:
    """对话轮次"""
    turn_id: int
    role: str  # user / assistant
    content: str
    intent: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    rag_results: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CompressedMemory:
    """压缩后的记忆（8段式结构化存储 - Claude Code风格）"""
    summary: str                          # 1. 核心摘要
    key_entities: List[str] = field(default_factory=list)  # 2. 关键实体
    discussed_topics: List[str] = field(default_factory=list)  # 3. 讨论话题
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # 4. 用户偏好
    resolved_issues: List[str] = field(default_factory=list)  # 5. 已解决问题
    pending_questions: List[str] = field(default_factory=list)  # 6. 待解决问题
    action_items: List[str] = field(default_factory=list)  # 7. 行动项
    context_continuity: str = ""          # 8. 上下文连续性标记
    original_turn_count: int = 0          # 原始轮次数量
    compression_ratio: float = 0.0       # 压缩比
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class UserProfile:
    """??????????"""
    user_id: str
    preferences: Dict[str, Any] = field(default_factory=dict)
    # key -> {"source": str, "confidence": float, "updated_at": str}
    preference_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # append-only history for preference updates
    preference_history: List[Dict[str, Any]] = field(default_factory=list)
    # conflict records when new value differs from old value
    preference_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    interaction_history: List[str] = field(default_factory=list)
    discussed_entities: Dict[str, List[str]] = field(default_factory=dict)  # entity -> topics
    satisfaction_scores: List[float] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

class ShortTermMemoryManager:
    """
    短期记忆管理器 - 当前对话

    功能：
    - 管理当前对话的所有轮次
    - 提取实体和意图
    - 计算上下文密度
    - 触发中期记忆压缩

    Claude Code 实现要点：
    - 实时访问最近 N 轮对话
    - 自动提取关键信息
    - 92% 阈值触发压缩
    """

    def __init__(
        self,
        max_turns: int = 50,
        compression_threshold: float = 0.92,
        max_context_tokens: int = 4000
    ):
        self.max_turns = max_turns
        self.compression_threshold = compression_threshold
        self.max_context_tokens = max_context_tokens

        self._lock = threading.RLock()
        self.turns: List[ConversationTurn] = []
        self.current_turn_id = 0

        self.entity_tracker: Dict[str, List[str]] = defaultdict(list)
        self.intent_history: List[str] = []
        self.topic_stack: List[str] = []

        self._tokenizer = self._init_tokenizer()

        logger.info(f"[ShortTermMemory] 初始化完成: max_turns={max_turns}, "
                   f"threshold={compression_threshold}")

    def _init_tokenizer(self):
        """初始化 tokenizer"""
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("[ShortTermMemory] tiktoken 初始化失败，使用简单分词")
            return None

    def add_turn(
        self,
        role: str,
        content: str,
        intent: Optional[str] = None,
        entities: List[str] = None,
        rag_results: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> ConversationTurn:
        """添加对话轮次"""
        with self._lock:
            turn = ConversationTurn(
                turn_id=self.current_turn_id,
                role=role,
                content=content,
                intent=intent,
                entities=entities or [],
                rag_results=rag_results or [],
                metadata=metadata or {}
            )

            self.turns.append(turn)
            self.current_turn_id += 1

            if intent:
                self.intent_history.append(intent)

            for entity in (entities or []):
                self.entity_tracker[entity].append(intent or "general")

            self._maintain_size_limit()

            logger.debug(f"[ShortTermMemory] 添加轮次: turn_id={turn.turn_id}, "
                        f"role={role}, intent={intent}, entities={entities}")
            return turn

    def _maintain_size_limit(self):
        """维护大小限制"""
        if len(self.turns) > self.max_turns:
            excess = len(self.turns) - self.max_turns
            self.turns = self.turns[excess:]
            logger.debug(f"[ShortTermMemory] 清理过期轮次: {excess} 条")

    def get_recent_turns(self, n: int = 10) -> List[ConversationTurn]:
        """获取最近的 N 轮对话"""
        with self._lock:
            return self.turns[-n:] if self.turns else []

    def get_context_for_llm(self, max_tokens: int = None) -> str:
        """生成 LLM 可用的上下文字符串"""
        with self._lock:
            max_tokens = max_tokens or self.max_context_tokens
            turns = self.get_recent_turns(20)

            context_parts = []
            current_tokens = 0

            for turn in reversed(turns):
                turn_text = f"{turn.role}: {turn.content}"
                turn_tokens = self._estimate_tokens(turn_text)

                if current_tokens + turn_tokens > max_tokens:
                    break

                context_parts.insert(0, turn_text)
                current_tokens += turn_tokens

            return "\n".join(context_parts)

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数量"""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        return len(text) // 4

    def calculate_density(self) -> float:
        """
        计算上下文密度

        返回值范围 [0, 1]：
        - 接近 1 表示上下文利用率高
        - 接近 0 表示上下文冗余或不足

        92% 阈值触发压缩（Claude Code）
        """
        with self._lock:
            if not self.turns:
                return 0.0

            total_tokens = sum(
                self._estimate_tokens(t.content) for t in self.turns
            )

            density = total_tokens / self.max_context_tokens
            return min(density, 1.0)

    def should_compress(self) -> bool:
        """判断是否应该触发压缩"""
        density = self.calculate_density()
        return density >= self.compression_threshold

    def extract_entities(self) -> Dict[str, int]:
        """提取并统计实体"""
        with self._lock:
            entity_counts = {}
            for entity, intents in self.entity_tracker.items():
                entity_counts[entity] = len(intents)
            return dict(sorted(entity_counts.items(), key=lambda x: x[1], reverse=True))

    def get_current_topic(self) -> Optional[str]:
        """获取当前讨论话题"""
        with self._lock:
            return self.topic_stack[-1] if self.topic_stack else None

    def push_topic(self, topic: str):
        """压入新话题"""
        with self._lock:
            if not self.topic_stack or self.topic_stack[-1] != topic:
                self.topic_stack.append(topic)
                logger.debug(f"[ShortTermMemory] 话题压入: {topic}")

    def pop_topic(self) -> Optional[str]:
        """弹出话题"""
        with self._lock:
            if self.topic_stack:
                return self.topic_stack.pop()
            return None


class MediumTermMemoryManager:
    """
    中期记忆管理器 - 智能压缩

    Claude Code 实现要点：
    - 92% 阈值自动触发智能压缩
    - 8 段式结构化保存核心信息
    - 保留语义连续性
    """

    def __init__(
        self,
        max_compressed_entries: int = 20,
        compression_ratio: float = 0.1  # 压缩到原来的 10%
    ):
        self.max_compressed_entries = max_compressed_entries
        self.compression_ratio = compression_ratio

        self._lock = threading.RLock()
        self.compressed_memories: List[CompressedMemory] = []

        logger.info(f"[MediumTermMemory] 初始化完成: "
                   f"max_entries={max_compressed_entries}, "
                   f"ratio={compression_ratio}")

    def compress(
        self,
        turns: List[ConversationTurn],
        strategy: CompressionStrategy = CompressionStrategy.SEMANTIC_SUMMARY
    ) -> CompressedMemory:
        """
        压缩对话历史为结构化记忆

        Args:
            turns: 待压缩的对话轮次
            strategy: 压缩策略

        Returns:
            压缩后的记忆
        """
        with self._lock:
            if not turns:
                return None

            if strategy == CompressionStrategy.SEMANTIC_SUMMARY:
                compressed = self._semantic_summary(turns)
            elif strategy == CompressionStrategy.STRUCTURED_EXTRACTION:
                compressed = self._structured_extraction(turns)
            elif strategy == CompressionStrategy.KEY_POINTS:
                compressed = self._key_points_extraction(turns)
            else:
                compressed = self._semantic_summary(turns)

            compressed.original_turn_count = len(turns)
            compressed.compression_ratio = self.compression_ratio

            self.compressed_memories.append(compressed)
            self._maintain_size_limit()

            logger.info(f"[MediumTermMemory] 压缩完成: "
                       f"{len(turns)} 轮 -> 摘要")

            return compressed

    def _semantic_summary(self, turns: List[ConversationTurn]) -> CompressedMemory:
        """语义摘要策略"""
        user_turns = [t for t in turns if t.role == "user"]
        assistant_turns = [t for t in turns if t.role == "assistant"]

        all_entities = []
        for t in turns:
            all_entities.extend(t.entities)

        entity_counts = {}
        for e in all_entities:
            entity_counts[e] = entity_counts.get(e, 0) + 1

        top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        intents = list(set(t.intent for t in turns if t.intent))

        compressed = CompressedMemory(
            summary=f"对话摘要：{len(turns)}轮对话，用户最关注: {', '.join([e[0] for e in top_entities[:3]])}",
            key_entities=[e[0] for e in top_entities[:5]],
            discussed_topics=intents[:5],
            user_preferences={},
            resolved_issues=[],
            pending_questions=[],
            action_items=[]
        )

        return compressed

    def _structured_extraction(self, turns: List[ConversationTurn]) -> CompressedMemory:
        """结构化提取策略"""
        compressed = CompressedMemory(
            summary="",
            key_entities=[],
            discussed_topics=[],
            user_preferences={},
            resolved_issues=[],
            pending_questions=[],
            action_items=[]
        )

        for turn in turns:
            if turn.intent == "troubleshooting":
                if "resolved" in turn.content.lower():
                    compressed.resolved_issues.append(turn.content[:100])
                else:
                    compressed.pending_questions.append(turn.content[:100])
            elif turn.intent == "purchase":
                compressed.action_items.append(turn.content[:100])

            compressed.key_entities.extend(turn.entities[:3])
            if turn.intent:
                compressed.discussed_topics.append(turn.intent)

        compressed.key_entities = list(set(compressed.key_entities))[:10]
        compressed.discussed_topics = list(set(compressed.discussed_topics))[:5]

        return compressed

    def _key_points_extraction(self, turns: List[ConversationTurn]) -> CompressedMemory:
        """关键点提取策略"""
        key_points = []

        for turn in turns:
            if turn.metadata.get("important"):
                key_points.append(turn.content[:200])

        return CompressedMemory(
            summary="关键点总结",
            key_entities=[],
            discussed_topics=[],
            user_preferences={},
            resolved_issues=[],
            pending_questions=[],
            action_items=key_points
        )

    def _maintain_size_limit(self):
        """维护大小限制"""
        if len(self.compressed_memories) > self.max_compressed_entries:
            self.compressed_memories = self.compressed_memories[-self.max_compressed_entries:]

    def get_recent_compressed(self, n: int = 5) -> List[CompressedMemory]:
        """获取最近 N 条压缩记忆"""
        with self._lock:
            return self.compressed_memories[-n:] if self.compressed_memories else []

    def get_all_summaries(self) -> str:
        """获取所有压缩记忆的摘要"""
        with self._lock:
            if not self.compressed_memories:
                return ""

            summaries = []
            for i, mem in enumerate(self.compressed_memories[-5:], 1):
                summaries.append(f"【记忆{i}】{mem.summary}")

            return "\n".join(summaries)


class LongTermMemoryManager:
    """
    长期记忆管理器 - 用户偏好和跨会话知识

    功能：
    - 持久化用户偏好
    - 跨会话恢复上下文
    - 用户画像管理

    存储方案：
    - Redis 主存储（SET/GET，原子写，跨进程安全）
    - JSON 文件兜底（Redis 不可用时自动回退）
    """

    def __init__(self, storage_path: str = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'data', 'memory', 'long_term'
            )

        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)

        self._lock = threading.RLock()
        self.user_profiles: Dict[str, UserProfile] = {}

        # Redis 连接（主存储）
        self._redis = None
        self._redis_available = False
        self._init_redis()

        logger.info(f"[LongTermMemory] 初始化完成: {storage_path}")

    def _init_redis(self):
        """初始化 Redis 连接"""
        try:
            from config.settings import settings
            import redis
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self._redis.ping()
            self._redis_available = True
            logger.info(f"[LongTermMemory] Redis 连接成功: {settings.redis_host}:{settings.redis_port}")
        except Exception as e:
            logger.warning(f"[LongTermMemory] Redis 连接失败，回退到文件存储: {e}")
            self._redis_available = False

    def _redis_key(self, user_id: str) -> str:
        """Redis 键名"""
        return f"memory:profile:{user_id}"

    def get_or_create_profile(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
        with self._lock:
            if user_id not in self.user_profiles:
                profile = self._load_profile(user_id)
                if profile is None:
                    profile = UserProfile(user_id=user_id)
                self.user_profiles[user_id] = profile

            return self.user_profiles[user_id]

    def _get_profile_path(self, user_id: str) -> str:
        """获取用户画像文件路径"""
        return os.path.join(self.storage_path, f"{user_id}_profile.json")

    def _load_profile(self, user_id: str) -> Optional[UserProfile]:
        """加载用户画像 — Redis 优先，文件兜底"""
        # 1. Redis 加载
        if self._redis_available:
            try:
                data_json = self._redis.get(self._redis_key(user_id))
                if data_json:
                    data = json.loads(data_json)
                    return UserProfile(**data)
            except Exception as e:
                logger.warning(f"[LongTermMemory] Redis 加载失败 {user_id}: {e}")

        # 2. 文件兜底（迁移/离线场景）
        try:
            path = self._get_profile_path(user_id)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "preference_meta" not in data:
                        data["preference_meta"] = {}
                    if "preference_history" not in data:
                        data["preference_history"] = []
                    if "preference_conflicts" not in data:
                        data["preference_conflicts"] = []
                    return UserProfile(**data)
        except Exception as e:
            logger.warning(f"[LongTermMemory] 文件加载失败 {user_id}: {e}")

        return None

    def save_profile(self, user_id: str) -> bool:
        """保存用户画像 — Redis 主存储 + JSON 文件兜底"""
        with self._lock:
            if user_id not in self.user_profiles:
                return False

            try:
                profile = self.user_profiles[user_id]
                profile.last_updated = datetime.now().isoformat()

                data = {
                    "user_id": profile.user_id,
                    "preferences": profile.preferences,
                    "preference_meta": profile.preference_meta,
                    "preference_history": profile.preference_history[-200:],
                    "preference_conflicts": profile.preference_conflicts[-200:],
                    "interaction_history": profile.interaction_history[-50:],
                    "discussed_entities": profile.discussed_entities,
                    "satisfaction_scores": profile.satisfaction_scores[-20:],
                    "created_at": profile.created_at,
                    "last_updated": profile.last_updated
                }
                json_str = json.dumps(data, ensure_ascii=False)

                # 1. Redis 写入（主存储）
                if self._redis_available:
                    self._redis.set(self._redis_key(user_id), json_str)

                # 2. JSON 文件写入（兜底 + 迁移兼容）
                path = self._get_profile_path(user_id)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(json_str)

                logger.info(f"[LongTermMemory] 保存成功: {user_id}")
                return True

            except Exception as e:
                logger.error(f"[LongTermMemory] 保存失败 {user_id}: {e}")
                return False

    def migrate_existing_to_redis(self, user_id: str = None) -> int:
        """
        将磁盘上的 JSON 文件批量迁移到 Redis

        用于首次切换存储时的数据迁移，后续正常读写走 save_profile 自动同步。

        Args:
            user_id: 指定用户迁移；None 则迁移 storage_path 下所有 JSON

        Returns:
            迁移的用户数
        """
        if not self._redis_available:
            logger.warning("[LongTermMemory] Redis 不可用，跳过迁移")
            return 0

        count = 0
        try:
            if user_id:
                # 单个用户 — 通过正常读写路径自动完成
                profile = self.get_or_create_profile(user_id)
                if profile:
                    self.save_profile(user_id)
                    count = 1
            else:
                # 批量迁移所有 JSON 文件
                for filename in os.listdir(self.storage_path):
                    if filename.endswith("_profile.json"):
                        uid = filename.replace("_profile.json", "")
                        profile = self.get_or_create_profile(uid)
                        if profile:
                            self.save_profile(uid)
                            count += 1

            logger.info(f"[LongTermMemory] Redis 迁移完成，共 {count} 个用户")
        except Exception as e:
            logger.error(f"[LongTermMemory] Redis 迁移失败: {e}")

        return count

    def update_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        source: str = "system_inferred",
        confidence: float = 0.6,
        importance: float = 0.5,
        ttl_seconds: Optional[int] = None,
        consent: bool = True,
    ):
        """?????????????"""
        profile = self.get_or_create_profile(user_id)
        now = datetime.now().isoformat()
        expires_at = (
            (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
            if ttl_seconds
            else None
        )
        normalized_importance = max(0.0, min(float(importance), 1.0))

        source_priority = {
            "explicit_user": 3,
            "authenticated_profile_sync": 2,
            "system_inferred": 1,
        }

        if not consent:
            profile.preference_history.append(
                {
                    "key": key,
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                    "importance": normalized_importance,
                    "ttl_seconds": ttl_seconds,
                    "consent": False,
                    "timestamp": now,
                    "skipped_reason": "missing_consent",
                }
            )
            return

        old_value = profile.preferences.get(key)
        old_meta = profile.preference_meta.get(key, {})
        old_source = old_meta.get("source", "system_inferred")
        old_confidence = float(old_meta.get("confidence", 0.0))

        history_entry = {
            "key": key,
            "value": value,
            "source": source,
            "confidence": confidence,
            "importance": normalized_importance,
            "ttl_seconds": ttl_seconds,
            "expires_at": expires_at,
            "consent": consent,
            "timestamp": now,
        }
        profile.preference_history.append(history_entry)
        if len(profile.preference_history) > 500:
            profile.preference_history = profile.preference_history[-500:]

        should_replace = False
        if old_value is None:
            should_replace = True
        elif old_value == value:
            should_replace = True
        else:
            conflict_record = {
                "key": key,
                "old_value": old_value,
                "new_value": value,
                "old_source": old_source,
                "new_source": source,
                "old_confidence": old_confidence,
                "new_confidence": confidence,
                "timestamp": now,
            }
            profile.preference_conflicts.append(conflict_record)
            if len(profile.preference_conflicts) > 500:
                profile.preference_conflicts = profile.preference_conflicts[-500:]

            new_priority = source_priority.get(source, 0)
            old_priority = source_priority.get(old_source, 0)
            if new_priority > old_priority:
                should_replace = True
            elif new_priority == old_priority and confidence >= old_confidence:
                should_replace = True

        if should_replace:
            profile.preferences[key] = value
            profile.preference_meta[key] = {
                "source": source,
                "confidence": confidence,
                "importance": normalized_importance,
                "ttl_seconds": ttl_seconds,
                "expires_at": expires_at,
                "consent": consent,
                "updated_at": now,
            }
            logger.debug(
                f"[LongTermMemory] preference updated: {user_id}.{key}={value} "
                f"(source={source}, confidence={confidence})"
            )
        else:
            logger.debug(
                f"[LongTermMemory] preference kept old value: {user_id}.{key} "
                f"(old_source={old_source}, new_source={source})"
            )

    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        profile = self.get_or_create_profile(user_id)
        return profile.preferences.get(key, default)

    def add_entity(self, user_id: str, entity: str, topic: str):
        """添加讨论过的实体"""
        profile = self.get_or_create_profile(user_id)

        if entity not in profile.discussed_entities:
            profile.discussed_entities[entity] = []

        if topic not in profile.discussed_entities[entity]:
            profile.discussed_entities[entity].append(topic)

        logger.debug(f"[LongTermMemory] 实体添加: {user_id}.{entity} -> {topic}")

    def get_user_context(self, user_id: str) -> str:
        """获取用户上下文（用于注入到 LLM）"""
        profile = self.get_or_create_profile(user_id)

        context_parts = []

        if profile.preferences:
            prefs_str = ", ".join(f"{k}={v}" for k, v in profile.preferences.items())
            context_parts.append(f"用户偏好: {prefs_str}")

        if profile.discussed_entities:
            recent_entities = list(profile.discussed_entities.keys())[-5:]
            entities_str = ", ".join(recent_entities)
            context_parts.append(f"历史讨论实体: {entities_str}")

        if profile.interaction_history:
            recent_interactions = profile.interaction_history[-3:]
            context_parts.append(f"最近交互: {'; '.join(recent_interactions)}")

        return "\n".join(context_parts) if context_parts else ""


class IntentEvolutionTracker:
    """
    意图演进跟踪器

    Manus 实现要点：
    - 通过复述操控注意力
    - 避免"丢失在中间"问题
    - 保持目标一致性
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.intent_sequence: List[Dict[str, Any]] = []
        self.current_goal: Optional[str] = None
        self.goal_history: List[str] = []

        logger.info("[IntentEvolution] 初始化完成")

    def track_intent(
        self,
        intent: str,
        confidence: float = 1.0,
        entities: List[str] = None
    ):
        """跟踪意图变化"""
        with self._lock:
            entry = {
                "intent": intent,
                "confidence": confidence,
                "entities": entities or [],
                "timestamp": datetime.now().isoformat()
            }

            self.intent_sequence.append(entry)

            if intent != self.current_goal:
                if self.current_goal:
                    self.goal_history.append(self.current_goal)
                self.current_goal = intent

            logger.debug(f"[IntentEvolution] 意图跟踪: {intent} (置信度: {confidence})")

    def detect_topic_shift(self) -> bool:
        """检测话题切换"""
        with self._lock:
            if len(self.intent_sequence) < 2:
                return False

            recent = self.intent_sequence[-1]["intent"]
            previous = self.intent_sequence[-2]["intent"]

            return recent != previous

    def get_continuity_context(self) -> str:
        """
        获取上下文连续性标记

        用于将目标复述到上下文的末尾（Manus 技巧）
        """
        with self._lock:
            if not self.current_goal:
                return ""

            recent_intents = [e["intent"] for e in self.intent_sequence[-5:]]

            context = f"[上下文连续性] 当前目标: {self.current_goal}"
            if self.goal_history:
                context += f" | 历史目标: {', '.join(self.goal_history[-2:])}"
            context += f" | 意图序列: {' -> '.join(recent_intents)}"

            return context

    def is_related_intent(self, intent1: str, intent2: str) -> bool:
        """判断两个意图是否相关"""
        related_groups = {
            "product_inquiry": ["price_inquiry", "product_spec", "comparison"],
            "price_inquiry": ["product_inquiry", "purchase", "discount"],
            "troubleshooting": ["product_spec", "comparison"],
            "purchase": ["price_inquiry", "discount"]
        }

        related = related_groups.get(intent1, [])
        return intent2 in related

    def get_context_for_topic_switch(
        self,
        old_topic: str,
        new_topic: str
    ) -> str:
        """获取话题切换时的补充上下文"""
        if self.is_related_intent(old_topic, new_topic):
            return f"继续讨论产品相关话题（从 {old_topic} 到 {new_topic}）"

        return f"话题切换：从 {old_topic} 到 {new_topic}"


class ContextWindowManager:
    """
    上下文窗口管理器

    LangChain 四类上下文管理方法：
    - Offload: 卸载信息到外部存储
    - Retrieve: 动态检索相关信息
    - Compress: 压缩上下文
    - Isolate: 分而治之
    """

    def __init__(
        self,
        max_tokens: int = 8000,
        reserve_tokens: int = 2000
    ):
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.available_tokens = max_tokens - reserve_tokens

        logger.info(f"[ContextWindow] 初始化完成: max={max_tokens}, "
                   f"reserve={reserve_tokens}")

    def estimate_tokens(self, text: str) -> int:
        """估算 token 数量"""
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return len(text) // 4

    def optimize_context(
        self,
        components: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        优化上下文组件

        Args:
            components: 上下文组件列表，每个包含:
                - content: 内容
                - importance: 重要性 (0-1)
                - flexible: 是否可压缩

        Returns:
            优化后的组件列表
        """
        total_tokens = sum(
            self.estimate_tokens(c.get("content", ""))
            for c in components
        )

        if total_tokens <= self.available_tokens:
            return components

        logger.info(f"[ContextWindow] 需要优化: {total_tokens} -> {self.available_tokens} tokens")

        sorted_components = sorted(
            components,
            key=lambda x: x.get("importance", 1.0),
            reverse=True
        )

        optimized = []
        current_tokens = 0

        for comp in sorted_components:
            comp_tokens = self.estimate_tokens(comp.get("content", ""))

            if current_tokens + comp_tokens <= self.available_tokens:
                optimized.append(comp)
                current_tokens += comp_tokens
            elif comp.get("flexible", False):
                compressed = self._compress_component(comp)
                if current_tokens + self.estimate_tokens(compressed) <= self.available_tokens:
                    optimized.append({"content": compressed, "importance": comp.get("importance", 0.5), "flexible": False})
                    current_tokens += self.estimate_tokens(compressed)

        return optimized

    def _compress_component(self, component: Dict[str, Any]) -> str:
        """压缩单个组件"""
        content = component.get("content", "")

        if len(content) <= 200:
            return content

        return content[:200] + "... [已压缩]"

    def should_offload(self, component: Dict[str, Any]) -> bool:
        """判断是否应该卸载到外部"""
        tokens = self.estimate_tokens(component.get("content", ""))
        return tokens > self.max_tokens * 0.8


class ContextEngineeringManager:
    """
    上下文工程管理器 - 统一管理三层记忆

    整合 Claude Code 和 Manus 的最佳实践：
    - 三层记忆架构
    - 智能压缩
    - 意图跟踪
    - 上下文优化
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True

        self.short_term = ShortTermMemoryManager(
            max_turns=50,
            compression_threshold=0.92,
            max_context_tokens=4000
        )

        self.medium_term = MediumTermMemoryManager(
            max_compressed_entries=20,
            compression_ratio=0.1
        )

        self.long_term = LongTermMemoryManager()

        self.intent_tracker = IntentEvolutionTracker()

        self.context_window = ContextWindowManager(
            max_tokens=8000,
            reserve_tokens=2000
        )

        logger.info("[ContextEngineering] 初始化完成 - 三层记忆架构")

    def add_turn(
        self,
        role: str,
        content: str,
        intent: Optional[str] = None,
        entities: List[str] = None,
        rag_results: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ):
        """添加对话轮次"""
        turn = self.short_term.add_turn(
            role=role,
            content=content,
            intent=intent,
            entities=entities,
            rag_results=rag_results,
            metadata=metadata
        )

        if intent:
            self.intent_tracker.track_intent(
                intent,
                confidence=metadata.get("confidence", 1.0) if metadata else 1.0,
                entities=entities
            )

        if self.short_term.should_compress():
            self._trigger_compression()

        return turn

    def _trigger_compression(self):
        """触发压缩"""
        logger.info("[ContextEngineering] 触发智能压缩")

        turns = self.short_term.get_recent_turns(50)
        if turns:
            compressed = self.medium_term.compress(turns)
            logger.info(f"[ContextEngineering] 压缩完成: {compressed.summary}")

    def get_unified_context(
        self,
        user_id: str = None,
        include_long_term: bool = True
    ) -> Dict[str, Any]:
        """
        获取统一上下文

        Returns:
            包含三层记忆的完整上下文
        """
        components = []

        short_context = self.short_term.get_context_for_llm()
        if short_context:
            components.append({
                "content": short_context,
                "importance": 1.0,
                "flexible": False,
                "tier": "short_term"
            })

        medium_summaries = self.medium_term.get_all_summaries()
        if medium_summaries:
            components.append({
                "content": medium_summaries,
                "importance": 0.7,
                "flexible": True,
                "tier": "medium_term"
            })

        if include_long_term and user_id:
            long_context = self.long_term.get_user_context(user_id)
            if long_context:
                components.append({
                    "content": long_context,
                    "importance": 0.8,
                    "flexible": True,
                    "tier": "long_term"
                })

        continuity = self.intent_tracker.get_continuity_context()
        if continuity:
            components.append({
                "content": continuity,
                "importance": 0.9,
                "flexible": False,
                "tier": "intent"
            })

        optimized = self.context_window.optimize_context(components)

        return {
            "short_term": self.short_term.get_recent_turns(10),
            "medium_term": self.medium_term.get_recent_compressed(3),
            "long_term": self.long_term.get_user_context(user_id) if user_id else "",
            "intent_continuity": continuity,
            "optimized_components": optimized,
            "stats": {
                "short_term_turns": len(self.short_term.turns),
                "compressed_memories": len(self.medium_term.compressed_memories),
                "density": self.short_term.calculate_density()
            }
        }

    def build_llm_prompt(
        self,
        user_id: str = None,
        system_prompt: str = ""
    ) -> str:
        """
        构建完整的 LLM 提示词

        Manus 技巧：
        - 将目标复述到上下文末尾
        - 保持 KV 缓存稳定
        """
        context = self.get_unified_context(user_id)

        prompt_parts = []

        if system_prompt:
            prompt_parts.append(f"【系统提示】\n{system_prompt}")

        if context["stats"]["short_term_turns"] > 0:
            turns = context["short_term"]
            turn_texts = [
                f"{t.role}: {t.content}"
                for t in turns
            ]
            prompt_parts.append(f"【当前对话】\n" + "\n".join(turn_texts))

        if context["medium_term"]:
            summaries = [
                m.summary for m in context["medium_term"]
            ]
            if summaries:
                prompt_parts.append(f"【历史摘要】\n" + "\n".join(summaries))

        if context["long_term"]:
            prompt_parts.append(f"【用户背景】\n{context['long_term']}")

        if context["intent_continuity"]:
            prompt_parts.append(f"【上下文连续性】\n{context['intent_continuity']}")

        return "\n\n".join(prompt_parts)

    def save_long_term_memory(self, user_id: str) -> bool:
        """保存长期记忆"""
        return self.long_term.save_profile(user_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "short_term": {
                "turn_count": len(self.short_term.turns),
                "density": self.short_term.calculate_density(),
                "should_compress": self.short_term.should_compress(),
                "entity_count": len(self.short_term.entity_tracker)
            },
            "medium_term": {
                "compressed_count": len(self.medium_term.compressed_memories),
                "compression_ratio": 0.1
            },
            "intent": {
                "current_goal": self.intent_tracker.current_goal,
                "goal_history_length": len(self.intent_tracker.goal_history)
            }
        }


context_engineering_manager = ContextEngineeringManager()
