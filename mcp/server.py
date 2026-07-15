"""
MCP Server 实现

提供本地 MCP 服务器，暴露工具给 MCP 客户端调用。

支持两种传输方式：
1. stdio: 通过标准输入输出通信
2. SSE: 通过 Server-Sent Events 通信
"""

import json
import asyncio
import sys
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from mcp.protocol import (
    MCPMessage,
    MCPMessageType,
    MCPToolCall,
    MCPToolResult,
    MCPError,
    MCPErrorCode,
    MCPInitializeResult,
    MCPCapabilities,
    MCPResource,
    MCPPrompt
)
from mcp.tools import MCPToolRegistry, tool_registry
from mcp.config import MCPSettings, get_mcp_settings
from core.logger import LoggerManager

logger = LoggerManager.get_logger("mcp_server")


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str = "test2langchain-mcp"
    version: str = "1.0.0"
    transport: str = "stdio"  # stdio | sse
    host: str = "localhost"
    port: int = 8765
    capabilities: MCPCapabilities = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = MCPCapabilities(
                tools=True,
                resources=True,
                prompts=False,
                logging=True
            )


class MCPServer:
    """
    MCP 服务器

    实现标准 MCP 协议服务器，处理客户端请求。
    """

    def __init__(
        self,
        config: Optional[MCPServerConfig] = None,
        tool_registry: Optional[MCPToolRegistry] = None
    ):
        self.config = config or MCPServerConfig()
        self.tool_registry = tool_registry or tool_registry
        self._running = False
        self._request_handlers: Dict[MCPMessageType, Callable] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._prompts: Dict[str, MCPPrompt] = {}

        self._setup_handlers()
        logger.info(f"[MCPServer] 初始化完成: {self.config.name} v{self.config.version}")

    def _setup_handlers(self):
        """设置请求处理器"""
        self._request_handlers = {
            MCPMessageType.INITIALIZE: self._handle_initialize,
            MCPMessageType.LIST_TOOLS: self._handle_list_tools,
            MCPMessageType.CALL_TOOL: self._handle_call_tool,
            MCPMessageType.LIST_RESOURCES: self._handle_list_resources,
            MCPMessageType.READ_RESOURCE: self._handle_read_resource,
            MCPMessageType.LIST_PROMPTS: self._handle_list_prompts,
            MCPMessageType.GET_PROMPT: self._handle_get_prompt,
        }

    async def start(self):
        """启动服务器"""
        if self._running:
            logger.warning("[MCPServer] 服务器已在运行")
            return

        self._running = True
        logger.info(f"[MCPServer] 启动服务器, transport={self.config.transport}")

        if self.config.transport == "stdio":
            await self._run_stdio()
        elif self.config.transport == "sse":
            await self._run_sse()
        else:
            raise ValueError(f"不支持的传输方式: {self.config.transport}")

    async def stop(self):
        """停止服务器"""
        self._running = False
        logger.info("[MCPServer] 服务器已停止")

    async def _run_stdio(self):
        """stdio 模式运行"""
        logger.info("[MCPServer] 以 stdio 模式运行")

        while self._running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None,
                    sys.stdin.readline
                )

                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                logger.debug(f"[MCPServer] 收到请求: {line}")

                try:
                    message = MCPMessage.from_json(line)
                    response = await self._handle_message(message)
                    response_json = response.to_json()
                    sys.stdout.write(response_json + "\n")
                    sys.stdout.flush()
                    logger.debug(f"[MCPServer] 发送响应: {response_json}")
                except json.JSONDecodeError as e:
                    error_response = MCPMessage.error_response(
                        request_id="",
                        error=MCPError(
                            code=MCPErrorCode.PARSE_ERROR,
                            message=f"JSON parse error: {str(e)}"
                        )
                    )
                    sys.stdout.write(error_response.to_json() + "\n")
                    sys.stdout.flush()

            except Exception as e:
                logger.error(f"[MCPServer] stdio 处理错误: {e}")
                break

    async def _run_sse(self):
        """SSE 模式运行（需要额外依赖）"""
        try:
            from fastapi import FastAPI, Request
            from fastapi.responses import StreamingResponse
            import uvicorn
        except ImportError:
            logger.error("[MCPServer] SSE 模式需要 fastapi 和 uvicorn")
            return

        app = FastAPI(title=self.config.name)

        @app.post("/message")
        async def handle_message(request: Request):
            body = await request.json()
            message = MCPMessage.from_json(json.dumps(body))
            response = await self._handle_message(message)
            return json.loads(response.to_json())

        @app.get("/sse")
        async def sse_endpoint():
            async def event_stream():
                while self._running:
                    await asyncio.sleep(1)
                    yield f"data: {{\"type\": \"ping\", \"timestamp\": \"{datetime.now().isoformat()}\"}}\n\n"

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream"
            )

        config = uvicorn.Config(
            app,
            host=self.config.host,
            port=self.config.port,
            log_level="warning"
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def _handle_message(self, message: MCPMessage) -> MCPMessage:
        """处理消息"""
        if message.error:
            return message

        if message.method is None:
            return MCPMessage.error_response(
                request_id=message.id or "",
                error=MCPError(
                    code=MCPErrorCode.INVALID_REQUEST,
                    message="Missing method"
                )
            )

        handler = self._request_handlers.get(message.method)
        if handler is None:
            return MCPMessage.error_response(
                request_id=message.id or "",
                error=MCPError(
                    code=MCPErrorCode.METHOD_NOT_FOUND,
                    message=f"Method not found: {message.method}"
                )
            )

        try:
            result = await handler(message.params or {})
            return MCPMessage.response(
                request_id=message.id,
                result=result
            )
        except Exception as e:
            logger.error(f"[MCPServer] 处理消息失败: {e}")
            return MCPMessage.error_response(
                request_id=message.id or "",
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message=str(e)
                )
            )

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理初始化请求"""
        logger.info(f"[MCPServer] 初始化请求: {params}")

        return MCPInitializeResult(
            capabilities=self.config.capabilities,
            server_info={
                "name": self.config.name,
                "version": self.config.version
            }
        ).to_dict()

    async def _handle_list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理列出工具请求"""
        tools = self.tool_registry.list_tools()
        return {
            "tools": [tool.to_dict() for tool in tools]
        }

    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理调用工具请求"""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name:
            raise ValueError("Missing tool name")

        call = MCPToolCall(name=name, arguments=arguments)
        result = await self.tool_registry.call_tool(call)

        return result.to_dict()

    async def _handle_list_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理列出资源请求"""
        return {
            "resources": [r.to_dict() for r in self._resources.values()]
        }

    async def _handle_read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理读取资源请求"""
        uri = params.get("uri")
        if not uri:
            raise ValueError("Missing resource URI")

        if uri not in self._resources:
            raise ValueError(f"Resource not found: {uri}")

        resource = self._resources[uri]
        return {
            "uri": uri,
            "name": resource.name,
            "contents": []
        }

    async def _handle_list_prompts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理列出提示词请求"""
        return {
            "prompts": [p.to_dict() for p in self._prompts.values()]
        }

    async def _handle_get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取提示词请求"""
        name = params.get("name")
        if not name:
            raise ValueError("Missing prompt name")

        if name not in self._prompts:
            raise ValueError(f"Prompt not found: {name}")

        prompt = self._prompts[name]
        return prompt.to_dict()

    def register_resource(self, resource: MCPResource) -> None:
        """注册资源"""
        self._resources[resource.uri] = resource
        logger.info(f"[MCPServer] 注册资源: {resource.uri}")

    def register_prompt(self, prompt: MCPPrompt) -> None:
        """注册提示词"""
        self._prompts[prompt.name] = prompt
        logger.info(f"[MCPServer] 注册提示词: {prompt.name}")


def create_mcp_server() -> MCPServer:
    """创建 MCP 服务器实例"""
    settings = get_mcp_settings()
    config = MCPServerConfig(
        name=settings.mcp_server_name,
        version=settings.mcp_server_version
    )
    return MCPServer(config=config)
