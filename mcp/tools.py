"""
MCP 工具适配器

将现有工具包装为 MCP 兼容的工具，支持注册、发现和调用。
"""

import json
import asyncio
import threading
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass, field
from datetime import datetime

from mcp.protocol import (
    MCPToolDefinition,
    MCPToolInputSchema,
    MCPToolCall,
    MCPToolResult,
    MCPError,
    MCPErrorCode
)
from core.logger import LoggerManager

logger = LoggerManager.get_logger("mcp_tools")


@dataclass
class MCPToolMetadata:
    """MCP 工具元数据"""
    name: str
    description: str
    input_schema: MCPToolInputSchema
    handler: Callable
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    timeout: int = 300


class MCPToolAdapter:
    """
    MCP 工具适配器

    将现有的 Python 函数包装为 MCP 兼容的工具。
    """

    def __init__(self):
        self._tools: Dict[str, MCPToolMetadata] = {}
        self._lock = threading.RLock()
        logger.info("[MCPToolAdapter] 初始化完成")

    def register(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: Optional[Dict[str, Any]] = None,
        required: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        timeout: int = 300
    ) -> None:
        """
        注册工具

        Args:
            name: 工具名称
            description: 工具描述
            handler: 处理函数
            input_schema: 输入参数 Schema
            required: 必需参数列表
            tags: 标签列表
            timeout: 超时时间
        """
        with self._lock:
            if input_schema is None:
                input_schema = {}

            schema = MCPToolInputSchema(
                type="object",
                properties=input_schema,
                required=required or []
            )

            metadata = MCPToolMetadata(
                name=name,
                description=description,
                input_schema=schema,
                handler=handler,
                tags=tags or [],
                timeout=timeout
            )

            self._tools[name] = metadata
            logger.info(f"[MCPToolAdapter] 注册工具: {name}")

    def unregister(self, name: str) -> bool:
        """注销工具"""
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info(f"[MCPToolAdapter] 注销工具: {name}")
                return True
            return False

    def get_tool(self, name: str) -> Optional[MCPToolMetadata]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self, tags: Optional[List[str]] = None) -> List[MCPToolDefinition]:
        """
        列出所有工具

        Args:
            tags: 可选的标签过滤

        Returns:
            工具定义列表
        """
        with self._lock:
            tools = []
            for metadata in self._tools.values():
                if tags and not any(tag in metadata.tags for tag in tags):
                    continue
                tools.append(MCPToolDefinition(
                    name=metadata.name,
                    description=metadata.description,
                    input_schema=metadata.input_schema
                ))
            return tools

    async def call_tool(self, call: MCPToolCall) -> MCPToolResult:
        """
        调用工具

        Args:
            call: 工具调用请求

        Returns:
            工具调用结果
        """
        logger.info(f"[MCPToolAdapter] 调用工具: {call.name}, 参数: {call.arguments}")

        metadata = self.get_tool(call.name)
        if metadata is None:
            logger.error(f"[MCPToolAdapter] 工具不存在: {call.name}")
            return MCPToolResult.error(
                call_id=call.call_id,
                error_message=f"Tool not found: {call.name}"
            )

        try:
            # 验证必需参数
            missing_params = []
            for param in metadata.input_schema.required:
                if param not in call.arguments:
                    missing_params.append(param)

            if missing_params:
                logger.error(f"[MCPToolAdapter] 缺少必需参数: {missing_params}")
                return MCPToolResult.error(
                    call_id=call.call_id,
                    error_message=f"Missing required parameters: {missing_params}"
                )

            # 执行工具
            handler = metadata.handler

            if asyncio.iscoroutinefunction(handler):
                result = await asyncio.wait_for(
                    handler(**call.arguments),
                    timeout=metadata.timeout
                )
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: handler(**call.arguments)
                )

            logger.info(f"[MCPToolAdapter] 工具调用成功: {call.name}")
            return MCPToolResult.success(
                call_id=call.call_id,
                content=result
            )

        except asyncio.TimeoutError:
            logger.error(f"[MCPToolAdapter] 工具超时: {call.name}")
            return MCPToolResult.error(
                call_id=call.call_id,
                error_message=f"Tool execution timeout after {metadata.timeout}s"
            )
        except Exception as e:
            logger.error(f"[MCPToolAdapter] 工具执行失败: {call.name}, 错误: {e}")
            return MCPToolResult.error(
                call_id=call.call_id,
                error_message=f"Tool execution error: {str(e)}"
            )


class MCPToolRegistry:
    """
    MCP 工具注册表

    全局工具注册表，管理所有 MCP 工具。
    """

    _instance = None
    _adapter: Optional[MCPToolAdapter] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapter = MCPToolAdapter()
        return cls._instance

    @property
    def adapter(self) -> MCPToolAdapter:
        return self._adapter

    def register(self, *args, **kwargs) -> None:
        """注册工具"""
        self._adapter.register(*args, **kwargs)

    def unregister(self, name: str) -> bool:
        """注销工具"""
        return self._adapter.unregister(name)

    def get_tool(self, name: str) -> Optional[MCPToolMetadata]:
        """获取工具"""
        return self._adapter.get_tool(name)

    def list_tools(self, tags: Optional[List[str]] = None) -> List[MCPToolDefinition]:
        """列出工具"""
        return self._adapter.list_tools(tags)

    async def call_tool(self, call: MCPToolCall) -> MCPToolResult:
        """调用工具"""
        return await self._adapter.call_tool(call)


# 全局工具注册表
tool_registry = MCPToolRegistry()


def mcp_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    required: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    timeout: int = 300
):
    """
    装饰器：将函数注册为 MCP 工具

    使用示例:
        @mcp_tool(
            description="查询天气",
            input_schema={
                "city": {"type": "string", "description": "城市名称"}
            },
            required=["city"]
        )
        def get_weather(city: str) -> dict:
            return {"city": city, "temperature": 25}
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_description = description or func.__doc__ or f"MCP Tool: {tool_name}"

        tool_registry.register(
            name=tool_name,
            description=tool_description,
            handler=func,
            input_schema=input_schema or {},
            required=required or [],
            tags=tags or [],
            timeout=timeout
        )

        return func

    return decorator


# 预定义的内置工具注册
def register_builtin_tools():
    """注册内置工具"""

    @mcp_tool(
        name="ping",
        description="健康检查工具，返回 pong",
        tags=["system"]
    )
    def ping() -> str:
        return "pong"

    @mcp_tool(
        name="get_server_time",
        description="获取服务器当前时间",
        tags=["system"]
    )
    def get_server_time() -> dict:
        return {
            "timestamp": datetime.now().isoformat(),
            "timezone": "UTC+8"
        }

    @mcp_tool(
        name="echo",
        description="回显消息",
        input_schema={
            "message": {"type": "string", "description": "要回显的消息"}
        },
        required=["message"],
        tags=["system"]
    )
    def echo(message: str) -> str:
        return message


# 初始化时注册内置工具
register_builtin_tools()
