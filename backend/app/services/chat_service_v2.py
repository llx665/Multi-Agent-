"""
聊天服务 V2 - 统一上下文管理 + SupervisorAgent 调度
强制优先使用知识库，确保回答基于检索结果

核心设计：
1. SessionContextManager: 统一管理所有会话的上下文
2. SupervisorAgent: 负责任务路由和结果整合
3. Memory 单一来源: 所有对话历史都存储在 SessionContext 中
"""

import sys
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.config import settings

# 核心组件
from core.session_context import SessionContext, SessionContextManager
from agents.supervisor_agent import SupervisorAgent

# RAG 组件 - 使用全局单例
from app.api.v1.knowledge_base import get_rag_tool

# LLM
from langchain_openai import ChatOpenAI

# 工具
from tools.amap_weather_tool import weather_tool
from tools.tavily_search_tool import search_tool
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field


class ChatServiceV2:
    """
    聊天服务 V2 - 统一上下文 + SupervisorAgent 调度

    核心流程：
    1. 获取/创建 SessionContext（统一上下文）
    2. 调用 SupervisorAgent.process()（意图识别 + 任务路由）
    3. SupervisorAgent 使用 SessionContext 中的 memory
    4. 返回结果并更新 SessionContext
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True

        # ========== 统一会话上下文管理器 ==========
        # 所有会话的上下文都通过这里管理
        self.session_manager = SessionContextManager()

        # ========== SupervisorAgent (Multi-Agent 调度器) ==========
        self.supervisor = SupervisorAgent()

        # ========== RAG 工具 ==========
        self.rag_tool: Optional[RAGTool] = None
        self._init_rag_tool()

        # ========== LLM (用于 RAG 查询增强) ==========
        self.llm = ChatOpenAI(
            api_key=settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0.1,
            streaming=False
        )

        print("[OK] ChatServiceV2 初始化完成 (统一上下文 + SupervisorAgent)")

    def _init_rag_tool(self):
        """初始化 RAG 工具"""
        try:
            self.rag_tool = get_rag_tool()
            self._load_documents()
            print("[OK] RAG 工具初始化完成")
        except Exception as e:
            print(f"[WARN] RAG 工具初始化失败: {e}")
            self.rag_tool = None

    def _load_documents(self):
        """加载知识库文档"""
        if not self.rag_tool:
            return

        try:
            docs_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                'data', 'docs'
            )

            if not os.path.exists(docs_dir):
                print(f"[WARN] 知识库目录不存在: {docs_dir}")
                return

            loaded_count = 0
            for filename in os.listdir(docs_dir):
                if filename.endswith(('.txt', '.pdf', '.docx')):
                    file_path = os.path.join(docs_dir, filename)
                    print(f"[DOC] 正在加载文档: {filename}")
                    try:
                        documents = self.rag_tool.load_document(file_path)
                        if documents:
                            self.rag_tool.add_documents_to_vector_db(documents)
                            loaded_count += len(documents)
                            print(f"   [OK] 已加载 {len(documents)} 个文档块")
                    except Exception as e:
                        print(f"   [ERR] 加载失败: {str(e)}")

            if loaded_count > 0:
                print(f"[OK] 知识库加载完成，共 {loaded_count} 个文档块")
            else:
                print("[WARN] 知识库为空")

        except Exception as e:
            print(f"[WARN] 加载知识库时出错: {str(e)}")

    async def process_message(
        self,
        session_id: str,
        message: str,
        history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        处理消息 - 统一上下文 + SupervisorAgent 调度

        Args:
            session_id: 会话 ID
            message: 用户消息
            history: 可选的外部历史记录（如果传入，会同步到 SessionContext）

        Returns:
            处理结果
        """
        try:
            # ========== 步骤 1: 获取/创建 SessionContext ==========
            # 优先使用 SessionContextManager 中的会话
            context = self.session_manager.get_session(session_id)

            if context is None:
                # 创建新会话
                context = self.session_manager.create_session(session_id)
                print(f"[Session] 创建新会话: {session_id}")
            else:
                print(f"[Session] 复用已有会话: {session_id}, 历史: {len(context.turn_history)} 条")

            # 如果传入了外部历史，同步到 SessionContext
            # （兼容旧 API）
            if history and len(history) > 0:
                self._sync_history_to_context(context, history, message)

            # ========== 步骤 2: RAG 检索（基于 SessionContext 的历史） ==========
            rag_result = await self._retrieve_with_rag(message, context)

            # 检查 RAG 结果是否与用户问题相关
            if rag_result.get("documents"):
                relevance = await self._check_rag_relevance(message, rag_result["documents"])
                if relevance < 0.3:
                    print(f"[RAG] 相关性分数 {relevance:.2f} 过低，忽略 RAG 结果")
                    rag_result = {"success": False, "documents": [], "has_relevant_info": False}
                else:
                    print(f"[RAG] 相关性分数 {relevance:.2f}，使用 RAG 结果")

            # 将 RAG 结果更新到 SessionContext
            if rag_result.get("documents"):
                context.update_rag_cache(message, rag_result["documents"])

            # ========== 步骤 3: 调用 SupervisorAgent ==========
            # SupervisorAgent 会：
            # 1. 使用 LLM 进行意图分类
            # 2. 根据意图路由到不同的 Skill
            # 3. Skill 使用 SessionContext 获取历史和上下文
            # 4. 整合结果并返回

            # 将 RAG 结果注入到 context 中，供 Skill 使用
            if rag_result.get("documents"):
                context.update_skill_context("rag", {
                    "documents": rag_result["documents"],
                    "has_relevant_info": rag_result.get("has_relevant_info", False),
                    "query": message
                })

            # 调用 SupervisorAgent 处理
            result = await self.supervisor.process(message, context)

            # ========== 步骤 4: 记录对话到 SessionContext ==========
            # SupervisorAgent.process() 已经添加了 user turn，
            # 这里添加 assistant turn
            context.add_turn(
                role="assistant",
                content=result.get("message", ""),
                agent_name="supervisor",
                intent=result.get("intent"),
                evaluation_score=result.get("evaluation_score", 0.0)
            )

            # ========== 步骤 5: 构建响应 ==========
            response_data = {
                "session_id": session_id,
                "message": result.get("message", ""),
                "intent": result.get("intent"),
                "confidence": result.get("confidence"),
                "customer_type": context.metadata.get("customer_type"),
                "skills_used": result.get("skills_used", []),
                "sources": result.get("sources", []),
                "timestamp": datetime.now(),
                "retrieved_documents": rag_result.get("documents", []),
                "retrieved_count": len(rag_result.get("documents", [])),
                "has_relevant_info": rag_result.get("has_relevant_info", False),
                "context_summary": self._get_context_summary(context)
            }

            print(f"\n[响应] 会话ID: {session_id}")
            print(f"   意图: {result.get('intent')} (置信度: {result.get('confidence', 0):.2f})")
            print(f"   客户类型: {context.metadata.get('customer_type')}")
            print(f"   Skills: {result.get('skills_used', [])}")
            print(f"   检索文档数: {len(rag_result.get('documents', []))}")

            return response_data

        except Exception as e:
            print(f"[ERR] 处理消息失败: {e}")
            import traceback
            traceback.print_exc()

            return {
                "session_id": session_id,
                "message": f"抱歉，处理您的请求时出现错误：{str(e)}",
                "intent": "error",
                "confidence": 0.0,
                "customer_type": None,
                "skills_used": [],
                "sources": [],
                "timestamp": datetime.now(),
                "retrieved_documents": [],
                "retrieved_count": 0,
                "has_relevant_info": False
            }

    async def _retrieve_with_rag(
        self,
        query: str,
        context: SessionContext
    ) -> Dict[str, Any]:
        """
        使用 RAG 检索知识库

        Args:
            query: 查询
            context: 会话上下文（用于获取历史）

        Returns:
            检索结果
        """
        if not self.rag_tool:
            return {"success": False, "documents": [], "has_relevant_info": False}

        try:
            # 从上下文获取对话历史用于查询增强
            chat_history = [
                {"role": t.role, "content": t.content}
                for t in context.turn_history[-6:]
            ]

            print(f"[RAG] 获取对话历史: {len(chat_history)} 条")
            if len(chat_history) > 0:
                print(f"[RAG] 最近一条: {chat_history[-1]['role']}: {chat_history[-1]['content'][:50]}...")

            # 从运行时参数管理器获取参数
            from app.api.v1.knowledge_base import rag_params_manager
            runtime_params = rag_params_manager.get_params()

            top_k = runtime_params.get('top_k', 5)
            enable_hybrid = runtime_params.get('enable_hybrid', True)

            # 执行检索（使用线程池因为 RAG 工具是同步的）
            loop = asyncio.get_event_loop()
            retrieval_result = await loop.run_in_executor(
                None,
                lambda: self.rag_tool.retrieve(
                    query=query,
                    top_k=top_k,
                    enable_self_rag=False,
                    llm=self.llm,
                    use_cache=True,
                    use_hybrid=enable_hybrid,
                    use_rerank=runtime_params.get('enable_rerank', True),
                    chat_history=chat_history
                )
            )

            documents = retrieval_result.get("documents", [])
            has_relevant_info = len(documents) > 0

            return {
                "success": retrieval_result.get("success", False),
                "documents": documents,
                "has_relevant_info": has_relevant_info,
                "enhanced_query": retrieval_result.get("contextualized_query")
            }

        except Exception as e:
            print(f"[ERR] RAG 检索失败: {e}")
            return {"success": False, "documents": [], "has_relevant_info": False}

    async def _check_rag_relevance(self, query: str, documents: List[Dict]) -> float:
        """
        检查 RAG 检索结果与用户查询的相关性

        Args:
            query: 用户查询
            documents: 检索到的文档列表

        Returns:
            相关性分数 0.0-1.0
        """
        if not documents:
            return 0.0

        query_lower = query.lower()
        query_keywords = set(query_lower.replace("?", "").replace("！", "").split())

        match_count = 0
        total_checks = 0

        for doc in documents[:3]:
            content = doc.get("content", "").lower()
            doc_keywords = set(content.replace(",", " ").replace("。", " ").replace("\n", " ").split())

            common = query_keywords & doc_keywords
            if len(query_keywords) > 0:
                keyword_match_ratio = len(common) / len(query_keywords)
            else:
                keyword_match_ratio = 0

            total_checks += 1
            if keyword_match_ratio > 0.1:
                match_count += keyword_match_ratio

        if total_checks > 0:
            return match_count / total_checks
        return 0.0

    def _sync_history_to_context(
        self,
        context: SessionContext,
        history: List[Dict[str, str]],
        current_message: str = None
    ):
        """
        将外部历史同步到 SessionContext

        Args:
            context: 会话上下文
            history: 外部历史记录
            current_message: 当前正在发送的消息（避免重复添加）
        """
        # 检查是否需要同步（避免重复添加）
        existing_history_len = len(context.turn_history)

        if existing_history_len == 0 and len(history) > 0:
            # 过滤掉最后一条（如果它就是当前消息）
            if current_message and len(history) > 0:
                last_msg = history[-1]
                if (last_msg.get("role") == "user" and
                    last_msg.get("content") == current_message):
                    # 不要添加最后一条，Supervisor 会添加
                    history_to_sync = history[:-1]
                else:
                    history_to_sync = history
            else:
                history_to_sync = history

            if len(history_to_sync) > 0:
                for msg in history_to_sync:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role in ["user", "assistant"]:
                        context.add_turn(
                            role=role,
                            content=content,
                            agent_name="history_sync"
                        )
                print(f"[Session] 从外部同步 {len(history_to_sync)} 条历史记录")

    def _get_context_summary(self, context: SessionContext) -> Dict[str, Any]:
        """获取上下文摘要"""
        return {
            "session_id": context.session_id,
            "turn_count": len(context.turn_history),
            "customer_type": context.metadata.get("customer_type"),
            "current_product": context.metadata.get("current_product"),
            "skills_used": list(set(
                t.agent_name for t in context.turn_history
                if t.agent_name and t.agent_name != "history_sync"
            )),
            "intents": list(set(
                t.intent for t in context.turn_history
                if t.intent
            ))
        }

    def get_session_history(self, session_id: str) -> List[Dict[str, str]]:
        """获取会话历史"""
        context = self.session_manager.get_session(session_id)
        if context is None:
            return []

        return [
            {"role": t.role, "content": t.content}
            for t in context.turn_history
        ]

    def clear_session(self, session_id: str) -> bool:
        """清除会话"""
        try:
            self.session_manager.delete_session(session_id)
            print(f"[Session] 会话已清除: {session_id}")
            return True
        except Exception as e:
            print(f"[ERR] 清除会话失败: {e}")
            return False


# 全局单例
chat_service_v2 = ChatServiceV2()
