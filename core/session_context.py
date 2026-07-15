"""
Unified session context manager with thread-safe three-tier memory integration.
"""

import json
import os
import re
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain.memory import ConversationBufferMemory

from core.logger import LoggerManager
from tools.rag.context_engineering import (
    CompressionStrategy,
    CompressedMemory,
    ConversationTurn,
    IntentEvolutionTracker,
    LongTermMemoryManager,
    MediumTermMemoryManager,
    ShortTermMemoryManager,
)

logger = LoggerManager.get_logger("session_context")


@dataclass
class TurnRecord:
    """Single conversation turn record."""

    role: str  # user / assistant
    content: str
    trace_id: Optional[str] = None
    agent_name: Optional[str] = None
    intent: Optional[str] = None
    rag_results: Optional[List[Dict]] = None
    evaluation_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class SessionContext:
    """Thread-safe session context with real three-tier memory."""

    def __init__(self, session_id: str, max_history: int = 50, user_id: Optional[str] = None):
        self.session_id = session_id
        self.user_id = user_id or session_id
        self.max_history = max_history
        self.created_at = datetime.now()
        self.updated_at = self.created_at

        self._lock = threading.RLock()
        self._storage_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "memory",
            "session_context",
        )
        os.makedirs(self._storage_path, exist_ok=True)

        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            max_len=max_history,
        )

        self.skill_context: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {
            "customer_type": None,
            "customer_name": None,
            "current_product": None,
            "preference": None,
            "discount_level": 1,
            "total_spent": 0.0,
        }

        self.turn_history: List[TurnRecord] = []
        self.rag_cache: Dict[str, Any] = {}

        # Real three-tier memory for this session.
        self.short_term_memory = ShortTermMemoryManager(
            max_turns=max_history * 2,
            compression_threshold=0.92,
            max_context_tokens=4000,
        )
        self.medium_term_memory = MediumTermMemoryManager(
            max_compressed_entries=20,
            compression_ratio=0.1,
        )
        self.long_term_memory = LongTermMemoryManager()
        self.intent_tracker = IntentEvolutionTracker()
        self._last_compressed_turn_id = -1

        self._restore_persistent_state()
        self._load_long_term_preferences()
        logger.info(f"[SessionContext] session created: {session_id}, user={self.user_id}")

    def bind_session(self, session_id: str) -> None:
        """Bind the latest active session id to this user context."""
        with self._lock:
            if session_id and self.session_id != session_id:
                self.session_id = session_id
                self.updated_at = datetime.now()
                self._persist_context_snapshot()

    def _get_context_snapshot_path(self) -> str:
        return os.path.join(self._storage_path, f"{self.user_id}_context.json")

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): self._make_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(item) for item in value]
        return str(value)

    def _rebuild_buffer_memory(self) -> None:
        self.memory.clear()
        for turn in self.turn_history:
            if turn.role == "user":
                self.memory.chat_memory.add_user_message(turn.content)
            else:
                self.memory.chat_memory.add_ai_message(turn.content)

    def _restore_persistent_state(self) -> None:
        path = self._get_context_snapshot_path()
        if not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception as exc:
            logger.warning(f"[SessionContext] failed to load snapshot for {self.user_id}: {exc}")
            return

        with self._lock:
            created_at = snapshot.get("created_at")
            updated_at = snapshot.get("updated_at")
            if created_at:
                try:
                    self.created_at = datetime.fromisoformat(created_at)
                except ValueError:
                    pass
            if updated_at:
                try:
                    self.updated_at = datetime.fromisoformat(updated_at)
                except ValueError:
                    self.updated_at = datetime.now()

            self.session_id = snapshot.get("session_id") or self.session_id
            self.metadata.update(snapshot.get("metadata") or {})
            self.skill_context = snapshot.get("skill_context") or {}
            self.rag_cache = snapshot.get("rag_cache") or {}

            self.turn_history = []
            for item in snapshot.get("turn_history", []):
                if not isinstance(item, dict):
                    continue
                self.turn_history.append(
                    TurnRecord(
                        role=item.get("role", "assistant"),
                        content=item.get("content", ""),
                        trace_id=item.get("trace_id"),
                        agent_name=item.get("agent_name"),
                        intent=item.get("intent"),
                        rag_results=item.get("rag_results") or [],
                        evaluation_score=float(item.get("evaluation_score", 0.0) or 0.0),
                        metadata=item.get("metadata") or {},
                        timestamp=item.get("timestamp") or datetime.now().isoformat(),
                    )
                )

            short_term_state = snapshot.get("short_term") or {}
            short_term_turns = []
            for item in short_term_state.get("turns", []):
                if not isinstance(item, dict):
                    continue
                short_term_turns.append(
                    ConversationTurn(
                        turn_id=int(item.get("turn_id", len(short_term_turns))),
                        role=item.get("role", "assistant"),
                        content=item.get("content", ""),
                        intent=item.get("intent"),
                        entities=list(item.get("entities") or []),
                        rag_results=item.get("rag_results") or [],
                        metadata=item.get("metadata") or {},
                        timestamp=item.get("timestamp") or datetime.now().isoformat(),
                    )
                )
            self.short_term_memory.turns = short_term_turns
            self.short_term_memory.current_turn_id = int(
                short_term_state.get("current_turn_id", len(short_term_turns))
            )

            entity_tracker = defaultdict(list)
            for key, value in (short_term_state.get("entity_tracker") or {}).items():
                entity_tracker[str(key)] = list(value or [])
            if not entity_tracker and short_term_turns:
                for turn in short_term_turns:
                    for entity in turn.entities:
                        entity_tracker[str(entity)].append(turn.intent or "general")
            self.short_term_memory.entity_tracker = entity_tracker
            self.short_term_memory.intent_history = list(
                short_term_state.get("intent_history")
                or [turn.intent for turn in short_term_turns if turn.intent]
            )
            self.short_term_memory.topic_stack = list(short_term_state.get("topic_stack") or [])

            medium_term_state = snapshot.get("medium_term") or {}
            medium_term_memories = []
            for item in medium_term_state.get("compressed_memories", []):
                if not isinstance(item, dict):
                    continue
                medium_term_memories.append(
                    CompressedMemory(
                        summary=item.get("summary", ""),
                        key_entities=list(item.get("key_entities") or []),
                        discussed_topics=list(item.get("discussed_topics") or []),
                        user_preferences=item.get("user_preferences") or {},
                        resolved_issues=list(item.get("resolved_issues") or []),
                        pending_questions=list(item.get("pending_questions") or []),
                        action_items=list(item.get("action_items") or []),
                        context_continuity=item.get("context_continuity", ""),
                        original_turn_count=int(item.get("original_turn_count", 0) or 0),
                        compression_ratio=float(item.get("compression_ratio", 0.0) or 0.0),
                        timestamp=item.get("timestamp") or datetime.now().isoformat(),
                    )
                )
            self.medium_term_memory.compressed_memories = medium_term_memories

            intent_state = snapshot.get("intent_tracker") or {}
            self.intent_tracker.intent_sequence = list(intent_state.get("intent_sequence") or [])
            self.intent_tracker.current_goal = intent_state.get("current_goal")
            self.intent_tracker.goal_history = list(intent_state.get("goal_history") or [])
            self._last_compressed_turn_id = int(snapshot.get("last_compressed_turn_id", -1) or -1)

            self._rebuild_buffer_memory()
            logger.info(f"[SessionContext] restored snapshot for user={self.user_id}")

    def get_persistent_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": 1,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "max_history": self.max_history,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
                "metadata": self._make_json_safe(self.metadata),
                "skill_context": self._make_json_safe(self.skill_context),
                "rag_cache": self._make_json_safe(self.rag_cache),
                "turn_history": [self._make_json_safe(asdict(turn)) for turn in self.turn_history],
                "short_term": {
                    "turns": [self._make_json_safe(asdict(turn)) for turn in self.short_term_memory.turns],
                    "current_turn_id": self.short_term_memory.current_turn_id,
                    "entity_tracker": self._make_json_safe(dict(self.short_term_memory.entity_tracker)),
                    "intent_history": self._make_json_safe(self.short_term_memory.intent_history),
                    "topic_stack": self._make_json_safe(self.short_term_memory.topic_stack),
                },
                "medium_term": {
                    "compressed_memories": [
                        self._make_json_safe(asdict(memory))
                        for memory in self.medium_term_memory.compressed_memories
                    ],
                },
                "intent_tracker": {
                    "intent_sequence": self._make_json_safe(self.intent_tracker.intent_sequence),
                    "current_goal": self.intent_tracker.current_goal,
                    "goal_history": self._make_json_safe(self.intent_tracker.goal_history),
                },
                "three_tier_summary": self.get_three_tier_context(),
                "last_compressed_turn_id": self._last_compressed_turn_id,
            }

    def _persist_context_snapshot(self) -> bool:
        with self._lock:
            self.updated_at = datetime.now()
            snapshot = self.get_persistent_snapshot()

        try:
            with open(self._get_context_snapshot_path(), "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            logger.error(f"[SessionContext] failed to persist snapshot for {self.user_id}: {exc}")
            return False

    def persist_context_snapshot(self) -> bool:
        return self._persist_context_snapshot()

    def delete_persisted_snapshot(self) -> bool:
        path = self._get_context_snapshot_path()
        if not os.path.exists(path):
            return True
        try:
            os.remove(path)
            return True
        except OSError as exc:
            logger.error(f"[SessionContext] failed to delete snapshot for {self.user_id}: {exc}")
            return False

    def _load_long_term_preferences(self) -> None:
        """Load persisted long-term profile into current metadata."""
        profile = self.long_term_memory.get_or_create_profile(self.user_id)
        for key in ["customer_type", "customer_name", "current_product", "preference", "total_spent", "discount_level"]:
            value = profile.preferences.get(key)
            if value is None:
                continue
            if key == "total_spent" and self.metadata.get(key, 0.0) != 0.0:
                continue
            if self.metadata.get(key) is None or self.metadata.get(key) == 0.0:
                self.metadata[key] = value

    def _extract_entities_from_text(self, content: str) -> List[str]:
        """Extract simple entities from text for memory indexing."""
        if not content:
            return []

        entities: List[str] = []

        model_pattern = r"\b[A-Za-z]+\d+[A-Za-z0-9\-\+]*\b"
        entities.extend(re.findall(model_pattern, content))

        english_phrase_pattern = r"\b[A-Za-z][A-Za-z0-9\-]{2,}\b"
        entities.extend(re.findall(english_phrase_pattern, content))

        seen = set()
        deduped = []
        for entity in entities:
            normalized = entity.strip()
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            deduped.append(normalized)

        return deduped[:8]

    def _sync_metadata_to_long_term(self) -> None:
        """Sync key metadata fields to long-term profile."""
        sync_keys = [
            "customer_type",
            "customer_name",
            "current_product",
            "preference",
            "discount_level",
            "service_strategy",
            "total_spent",
        ]

        for key in sync_keys:
            value = self.metadata.get(key)
            if value is None:
                continue
            if key == "total_spent" and float(value or 0) <= 0:
                continue
            self.long_term_memory.update_preference(
                self.user_id,
                key,
                value,
                source="authenticated_profile_sync",
                confidence=0.7,
            )

        discussed_products = self.metadata.get("discussed_products", [])
        if isinstance(discussed_products, list):
            for product in discussed_products[-20:]:
                if product:
                    self.long_term_memory.add_entity(self.user_id, str(product), "discussed_product")

    def _try_compress_short_term(self) -> None:
        """Compress short-term memory into medium-term memory when threshold is reached."""
        if not self.short_term_memory.should_compress():
            return

        recent_turns = self.short_term_memory.get_recent_turns(self.max_history * 2)
        if not recent_turns:
            return

        latest_turn_id = recent_turns[-1].turn_id
        if latest_turn_id <= self._last_compressed_turn_id:
            return

        compressed = self.medium_term_memory.compress(
            recent_turns,
            strategy=CompressionStrategy.SEMANTIC_SUMMARY,
        )
        if not compressed:
            return

        self._last_compressed_turn_id = latest_turn_id
        self.metadata["compressed_memory_count"] = len(self.medium_term_memory.compressed_memories)
        self.metadata["last_compressed_summary"] = compressed.summary

        self.skill_context["three_tier_medium_memory"] = {
            "data": {
                "summary": compressed.summary,
                "key_entities": compressed.key_entities,
                "discussed_topics": compressed.discussed_topics,
                "timestamp": compressed.timestamp,
            },
            "timestamp": datetime.now().isoformat(),
            "metadata": {"source": "auto_compression"},
        }

        logger.info(
            "[SessionContext] medium-term compression triggered: "
            f"turn_id={latest_turn_id}, compressed_count={len(self.medium_term_memory.compressed_memories)}"
        )

    def add_turn(
        self,
        role: str,
        content: str,
        agent_name: str = None,
        intent: str = None,
        rag_results: List[Dict] = None,
        evaluation_score: float = 0.0,
        metadata: Dict[str, Any] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """Add one turn and update all context layers."""
        with self._lock:
            active_trace_id = trace_id or (metadata or {}).get("trace_id") or self.metadata.get("trace_id")
            turn = TurnRecord(
                role=role,
                content=content,
                trace_id=active_trace_id,
                agent_name=agent_name,
                intent=intent,
                rag_results=rag_results,
                evaluation_score=evaluation_score,
                metadata=metadata or {},
            )
            self.turn_history.append(turn)
            if active_trace_id:
                self.metadata["trace_id"] = active_trace_id

            if role == "user":
                self.memory.chat_memory.add_user_message(content)
            else:
                self.memory.chat_memory.add_ai_message(content)

            if len(self.turn_history) > self.max_history * 2:
                self.turn_history = self.turn_history[-self.max_history :]

            raw_entities = (metadata or {}).get("entities", [])
            entities = raw_entities if isinstance(raw_entities, list) and raw_entities else self._extract_entities_from_text(content)

            confidence = (metadata or {}).get("confidence", 1.0)
            self.short_term_memory.add_turn(
                role=role,
                content=content,
                intent=intent,
                entities=entities,
                rag_results=rag_results,
                metadata=metadata or {},
            )

            if intent:
                self.intent_tracker.track_intent(
                    intent=intent,
                    confidence=confidence,
                    entities=entities,
                )

            if role == "user":
                profile = self.long_term_memory.get_or_create_profile(self.user_id)
                profile.interaction_history.append(content[:200])
                for entity in entities[:5]:
                    self.long_term_memory.add_entity(self.user_id, entity, intent or "general")

            self._try_compress_short_term()
            self._persist_context_snapshot()

    def update_skill_context(
        self,
        skill_name: str,
        result_data: Any,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Update skill context and sync structured fields to metadata/long-term memory."""
        with self._lock:
            self.skill_context[skill_name] = {
                "data": result_data,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {},
            }

            if skill_name == "customer_classifier" and isinstance(result_data, dict):
                if "customer_type" in result_data:
                    self.metadata["customer_type"] = result_data["customer_type"]
                if "strategy" in result_data:
                    self.metadata["service_strategy"] = result_data["strategy"]

            elif skill_name == "negotiation" and isinstance(result_data, dict):
                product_data = result_data.get("product", {})
                if "name" in product_data:
                    self.metadata["current_product"] = product_data["name"]
                if "discount_level" in result_data:
                    self.metadata["discount_level"] = result_data["discount_level"]

            elif skill_name == "sales_agent" and isinstance(result_data, dict):
                product_data = result_data.get("product", {})
                if isinstance(product_data, dict) and product_data.get("name"):
                    self.metadata["current_product"] = product_data.get("name")

            self._sync_metadata_to_long_term()
            self._persist_context_snapshot()
            logger.debug(f"[SessionContext] skill context updated: {skill_name}")

    def get_skill_context(self, skill_name: str) -> Optional[Any]:
        """Get one skill context entry."""
        with self._lock:
            value = self.skill_context.get(skill_name)
            if isinstance(value, dict) and "data" in value:
                return value.get("data")
            return value

    def get_three_tier_context(self) -> Dict[str, Any]:
        """Return a serializable snapshot of short/medium/long-term memory."""
        with self._lock:
            short_turns = self.short_term_memory.get_recent_turns(10)
            medium_memories = self.medium_term_memory.get_recent_compressed(3)
            long_term_text = self.long_term_memory.get_user_context(self.user_id)
            medium_summary = self.medium_term_memory.get_all_summaries()
            intent_continuity = self.intent_tracker.get_continuity_context()

            return {
                "short_term_turns": [
                    {
                        "turn_id": t.turn_id,
                        "role": t.role,
                        "content": t.content,
                        "intent": t.intent,
                        "entities": list(t.entities),
                        "timestamp": t.timestamp,
                    }
                    for t in short_turns
                ],
                "medium_term_memories": [
                    {
                        "summary": m.summary,
                        "key_entities": list(m.key_entities),
                        "discussed_topics": list(m.discussed_topics),
                        "timestamp": m.timestamp,
                        "original_turn_count": m.original_turn_count,
                        "compression_ratio": m.compression_ratio,
                    }
                    for m in medium_memories
                ],
                "medium_term_summary": medium_summary,
                "long_term_text": long_term_text,
                "intent_continuity": intent_continuity,
                "stats": {
                    "short_term_turns": len(self.short_term_memory.turns),
                    "compressed_memories": len(self.medium_term_memory.compressed_memories),
                    "density": self.short_term_memory.calculate_density(),
                },
            }

    def persist_long_term_memory(self) -> bool:
        """Persist long-term profile to disk."""
        with self._lock:
            self._sync_metadata_to_long_term()
            long_term_saved = self.long_term_memory.save_profile(self.user_id)
        snapshot_saved = self._persist_context_snapshot()
        return long_term_saved and snapshot_saved

    def get_unified_context(self) -> Dict[str, Any]:
        """Get unified context for downstream routing and skills."""
        with self._lock:
            three_tier_context = self.get_three_tier_context()
            return {
                "session_id": self.session_id,
                "trace_id": self.metadata.get("trace_id"),
                "user_id": self.user_id,
                "memory": self.memory.load_memory_variables({}),
                "skill_context": dict(self.skill_context),
                "metadata": dict(self.metadata),
                "three_tier_context": three_tier_context,
                "recent_history": [{"role": t.role, "content": t.content} for t in self.turn_history[-10:]],
            }

    def get_context_for_skill(self, skill_name: str) -> Dict[str, Any]:
        """Get context payload for one skill."""
        with self._lock:
            unified = self.get_unified_context()
            skill_context = unified.get("skill_context", {})
            three_tier_context = unified.get("three_tier_context", {})

            history = [{"role": t.role, "content": t.content} for t in self.turn_history[-6:]]

            return {
                "query": unified["recent_history"][-1]["content"] if unified["recent_history"] else "",
                "history": history,
                "rag_results": self.rag_cache.get("recent_rag_results", []),
                "customer_type": self.metadata.get("customer_type"),
                "current_product": self.metadata.get("current_product"),
                "preference": self.metadata.get("preference"),
                "discount_level": self.metadata.get("discount_level", 1),
                "trace_id": self.metadata.get("trace_id"),
                "three_tier_context": three_tier_context,
                "medium_term_summary": three_tier_context.get("medium_term_summary", ""),
                "long_term_context": three_tier_context.get("long_term_text", ""),
                "intent_continuity": three_tier_context.get("intent_continuity", ""),
                **{f"{skill_name}_result": skill_context.get(skill_name)},
            }

    def update_rag_cache(self, query: str, results: List[Dict]) -> None:
        """Update RAG cache in this session."""
        with self._lock:
            self.rag_cache["last_query"] = query
            self.rag_cache["last_rag_results"] = results
            self.rag_cache["recent_rag_results"] = results
            self._persist_context_snapshot()

    def get_average_evaluation_score(self) -> float:
        """Get average non-zero evaluation score."""
        with self._lock:
            if not self.turn_history:
                return 0.0

            scores = [t.evaluation_score for t in self.turn_history if t.evaluation_score > 0]
            return sum(scores) / len(scores) if scores else 0.0

    def get_session_summary(self) -> Dict[str, Any]:
        """Get session summary with three-tier memory stats."""
        with self._lock:
            total_turns = len(self.turn_history)
            user_turns = sum(1 for t in self.turn_history if t.role == "user")
            assistant_turns = total_turns - user_turns

            skills_used = list(
                set(
                    t.agent_name
                    for t in self.turn_history
                    if t.agent_name and t.agent_name != "general"
                )
            )

            intents_detected = list(set(t.intent for t in self.turn_history if t.intent))
            three_tier = self.get_three_tier_context()

            return {
                "session_id": self.session_id,
                "trace_id": self.metadata.get("trace_id"),
                "user_id": self.user_id,
                "created_at": self.created_at.isoformat(),
                "duration_seconds": (datetime.now() - self.created_at).total_seconds(),
                "total_turns": total_turns,
                "user_turns": user_turns,
                "assistant_turns": assistant_turns,
                "skills_used": skills_used,
                "intents_detected": intents_detected,
                "customer_type": self.metadata.get("customer_type"),
                "current_product": self.metadata.get("current_product"),
                "avg_evaluation_score": round(self.get_average_evaluation_score(), 3),
                "metadata": dict(self.metadata),
                "three_tier_stats": three_tier.get("stats", {}),
            }

    def clear(self, remove_persisted: bool = False) -> None:
        """Clear in-memory session state."""
        with self._lock:
            self.memory.clear()
            self.skill_context.clear()
            self.turn_history.clear()
            self.rag_cache.clear()
            self.metadata = {
                "customer_type": None,
                "customer_name": None,
                "current_product": None,
                "preference": None,
                "discount_level": 1,
                "total_spent": 0.0,
            }

            self.short_term_memory = ShortTermMemoryManager(
                max_turns=self.max_history * 2,
                compression_threshold=0.92,
                max_context_tokens=4000,
            )
            self.medium_term_memory = MediumTermMemoryManager(
                max_compressed_entries=20,
                compression_ratio=0.1,
            )
            self.intent_tracker = IntentEvolutionTracker()
            self._last_compressed_turn_id = -1

            logger.info(f"[SessionContext] session cleared: {self.session_id}")

        if remove_persisted:
            self.delete_persisted_snapshot()
        else:
            self._persist_context_snapshot()


class SessionContextManager:
    """Thread-safe singleton manager for all session contexts."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._sessions_lock = threading.RLock()
            self._sessions: Dict[str, SessionContext] = {}
            self._user_sessions: Dict[str, SessionContext] = {}
            logger.info("[SessionContextManager] initialized")

    def create_session(
        self,
        session_id: str,
        max_history: int = 50,
        user_id: Optional[str] = None,
    ) -> SessionContext:
        """Create or get one session context."""
        with self._sessions_lock:
            if user_id and user_id in self._user_sessions:
                context = self._user_sessions[user_id]
                self._sessions[session_id] = context
                context.bind_session(session_id)
                logger.info(f"[SessionContextManager] rebound session {session_id} -> user {user_id}")
                return context

            if session_id not in self._sessions:
                context = SessionContext(
                    session_id=session_id,
                    max_history=max_history,
                    user_id=user_id,
                )
                self._sessions[session_id] = context
                if user_id:
                    self._user_sessions[user_id] = context
                logger.info(f"[SessionContextManager] created session: {session_id}")
            return self._sessions[session_id]

    def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[SessionContext]:
        """Get an existing session context."""
        with self._sessions_lock:
            if user_id and user_id in self._user_sessions:
                return self._user_sessions.get(user_id)
            return self._sessions.get(session_id)

    def get_session_by_user(self, user_id: str) -> Optional[SessionContext]:
        with self._sessions_lock:
            return self._user_sessions.get(user_id)

    def list_user_ids(self) -> List[str]:
        with self._sessions_lock:
            return list(self._user_sessions.keys())

    def delete_session(self, session_id: str, user_id: Optional[str] = None, remove_persisted: bool = True) -> bool:
        """Delete one session context."""
        with self._sessions_lock:
            context = self.get_session(session_id, user_id=user_id)
            if context is None:
                return False

            aliases = [sid for sid, active_context in self._sessions.items() if active_context is context]
            for alias in aliases:
                del self._sessions[alias]

            user_key = context.user_id
            if user_key in self._user_sessions and self._user_sessions[user_key] is context:
                del self._user_sessions[user_key]

        context.clear(remove_persisted=remove_persisted)
        logger.info(f"[SessionContextManager] deleted session: {session_id}")
        return True

    def list_sessions(self) -> List[str]:
        """List all live session IDs."""
        with self._sessions_lock:
            return list(self._sessions.keys())

    def get_all_sessions_summary(self) -> List[Dict[str, Any]]:
        """Get summary for all sessions."""
        with self._sessions_lock:
            unique_contexts = list({id(session): session for session in self._sessions.values()}.values())
            return [session.get_session_summary() for session in unique_contexts]


session_context_manager = SessionContextManager()
