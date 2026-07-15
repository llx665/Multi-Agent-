"""
MCP 工具集成

将现有项目工具包装为 MCP 兼容工具。
"""

import os
import sys
from typing import Any, Dict, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp.tools import mcp_tool, tool_registry
from mcp.protocol import MCPToolDefinition, MCPToolInputSchema
from core.logger import LoggerManager

logger = LoggerManager.get_logger("mcp_integrations")


def register_rag_tools():
    """注册 RAG 相关工具"""

    @mcp_tool(
        name="rag_search",
        description="在知识库中搜索相关文档",
        input_schema={
            "query": {
                "type": "string",
                "description": "搜索查询"
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认5",
                "default": 5
            },
            "use_hybrid": {
                "type": "boolean",
                "description": "是否使用混合检索（向量+BM25）",
                "default": True
            }
        },
        required=["query"],
        tags=["rag", "search"]
    )
    async def rag_search(
        query: str,
        top_k: int = 5,
        use_hybrid: bool = True
    ) -> Dict[str, Any]:
        """在知识库中搜索"""
        try:
            from backend.app.api.v1.knowledge_base import get_rag_tool
            rag_tool = get_rag_tool()

            if not rag_tool:
                return {
                    "success": False,
                    "error": "RAG 工具未初始化"
                }

            result = rag_tool.retrieve(
                query=query,
                top_k=top_k,
                use_hybrid=use_hybrid,
                use_cache=True
            )

            return {
                "success": result.get("success", False),
                "documents": result.get("documents", [])[:top_k],
                "total_count": len(result.get("documents", []))
            }
        except Exception as e:
            logger.error(f"[rag_search] 搜索失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "documents": []
            }

    @mcp_tool(
        name="rag_add_document",
        description="添加文档到知识库",
        input_schema={
            "file_path": {
                "type": "string",
                "description": "文档文件路径"
            }
        },
        required=["file_path"],
        tags=["rag", "admin"]
    )
    async def rag_add_document(file_path: str) -> Dict[str, Any]:
        """添加文档到知识库"""
        try:
            from backend.app.api.v1.knowledge_base import get_rag_tool
            rag_tool = get_rag_tool()

            if not rag_tool:
                return {
                    "success": False,
                    "error": "RAG 工具未初始化"
                }

            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"文件不存在: {file_path}"
                }

            documents = rag_tool.load_document(file_path)
            if documents:
                rag_tool.add_documents_to_vector_db(documents)
                return {
                    "success": True,
                    "document_count": len(documents),
                    "message": f"成功添加 {len(documents)} 个文档块"
                }
            else:
                return {
                    "success": False,
                    "error": "无法加载文档"
                }
        except Exception as e:
            logger.error(f"[rag_add_document] 添加失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }


def register_weather_tools():
    """注册天气相关工具"""

    @mcp_tool(
        name="get_weather",
        description="获取指定城市的天气信息",
        input_schema={
            "city": {
                "type": "string",
                "description": "城市名称（中文或拼音）"
            }
        },
        required=["city"],
        tags=["weather", "api"]
    )
    async def get_weather(city: str) -> Dict[str, Any]:
        """获取天气信息"""
        try:
            from tools.amap_weather_tool import weather_tool

            result = weather_tool.get_weather(city)
            return {
                "success": result.get("success", False),
                "city": city,
                "weather": result.get("data"),
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(f"[get_weather] 获取天气失败: {e}")
            return {
                "success": False,
                "city": city,
                "error": str(e)
            }


def register_search_tools():
    """注册搜索相关工具"""

    @mcp_tool(
        name="web_search",
        description="使用 Tavily 进行网络搜索",
        input_schema={
            "query": {
                "type": "string",
                "description": "搜索查询"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数",
                "default": 5
            }
        },
        required=["query"],
        tags=["search", "web"]
    )
    async def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
        """网络搜索"""
        try:
            from tools.tavily_search_tool import search_tool

            result = search_tool.search(query, max_results=max_results)
            return {
                "success": result.get("success", False),
                "query": query,
                "results": result.get("results", []),
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(f"[web_search] 搜索失败: {e}")
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "results": []
            }


def register_chat_tools():
    """注册聊天相关工具"""

    @mcp_tool(
        name="chat",
        description="与智能客服进行对话",
        input_schema={
            "message": {
                "type": "string",
                "description": "用户消息"
            },
            "session_id": {
                "type": "string",
                "description": "会话ID，用于保持上下文",
                "default": "default"
            }
        },
        required=["message"],
        tags=["chat", "ai"]
    )
    async def chat(message: str, session_id: str = "default") -> Dict[str, Any]:
        """聊天对话"""
        try:
            from backend.app.services.chat_service_v3 import chat_service_v3

            result = await chat_service_v3.process_message(
                session_id=session_id,
                message=message
            )

            return {
                "success": True,
                "message": result.get("message", ""),
                "intent": result.get("intent"),
                "confidence": result.get("confidence"),
                "sources": result.get("sources", [])
            }
        except Exception as e:
            logger.error(f"[chat] 对话失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "抱歉，处理您的请求时出现错误"
            }

    @mcp_tool(
        name="clear_session",
        description="清除会话上下文",
        input_schema={
            "session_id": {
                "type": "string",
                "description": "会话ID"
            }
        },
        required=["session_id"],
        tags=["chat", "session"]
    )
    async def clear_session(session_id: str) -> Dict[str, Any]:
        """清除会话"""
        try:
            from backend.app.services.chat_service_v3 import chat_service_v3

            success = chat_service_v3.clear_session(session_id)
            return {
                "success": success,
                "session_id": session_id,
                "message": "会话已清除" if success else "会话不存在"
            }
        except Exception as e:
            logger.error(f"[clear_session] 清除失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }


def register_session_tools():
    """注册会话管理工具"""

    @mcp_tool(
        name="get_session_history",
        description="获取会话历史记录",
        input_schema={
            "session_id": {
                "type": "string",
                "description": "会话ID"
            }
        },
        required=["session_id"],
        tags=["session", "history"]
    )
    async def get_session_history(session_id: str) -> Dict[str, Any]:
        """获取会话历史"""
        try:
            from backend.app.services.chat_service_v3 import chat_service_v3

            history = chat_service_v3.get_session_history(session_id)
            return {
                "success": True,
                "session_id": session_id,
                "history": history,
                "turn_count": len(history)
            }
        except Exception as e:
            logger.error(f"[get_session_history] 获取失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "history": []
            }


def register_all_tools():
    """注册所有工具"""
    logger.info("[MCP Integrations] 开始注册工具...")

    try:
        register_rag_tools()
        logger.info("[MCP Integrations] RAG 工具注册完成")
    except Exception as e:
        logger.warning(f"[MCP Integrations] RAG 工具注册失败: {e}")

    try:
        register_weather_tools()
        logger.info("[MCP Integrations] 天气工具注册完成")
    except Exception as e:
        logger.warning(f"[MCP Integrations] 天气工具注册失败: {e}")

    try:
        register_search_tools()
        logger.info("[MCP Integrations] 搜索工具注册完成")
    except Exception as e:
        logger.warning(f"[MCP Integrations] 搜索工具注册失败: {e}")

    try:
        register_chat_tools()
        logger.info("[MCP Integrations] 聊天工具注册完成")
    except Exception as e:
        logger.warning(f"[MCP Integrations] 聊天工具注册失败: {e}")

    try:
        register_session_tools()
        logger.info("[MCP Integrations] 会话工具注册完成")
    except Exception as e:
        logger.warning(f"[MCP Integrations] 会话工具注册失败: {e}")

    logger.info(f"[MCP Integrations] 工具注册完成，共 {len(tool_registry.list_tools())} 个工具")


def get_mcp_tool_definitions() -> List[MCPToolDefinition]:
    """获取所有 MCP 工具定义"""
    return tool_registry.list_tools()
