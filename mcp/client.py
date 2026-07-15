"""
MCP Client 实现

提供 MCP 客户端，用于连接外部 MCP 服务器并调用工具。

支持两种传输方式：
1. stdio: 启动子进程并通过标准输入输出通信
2. SSE: 通过 Server-Sent Events 连接远程服务器
"""

import json
import asyncio
import subprocess
import sys
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mcp.protocol import (
    MCPMessage,
    MCPMessageType,
    MCPToolCall,
    MCPToolResult,
    MCPToolDefinition,
    MCPError,
    MCPErrorCode,
    MCPInitializeResult,
    MCPCapabilities
)
from mcp.config import MCPSettings, MCPServerConnectionConfig, get_mcp_settings
from core.logger import LoggerManager

logger = LoggerManager.get_logger("mcp_client")


@dataclass
class MCPConnectionConfig:
    """MCP 连接配置"""
    name: str
    transport: str = "stdio"
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    url: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30

    @classmethod
    def from_server_config(cls, config: MCPServerConnectionConfig) -> "MCPConnectionConfig":
        """从服务器配置创建连接配置"""
        return cls(
            name=config.name,
            transport=config.transport,
            command=config.command,
            args=config.args,
            url=config.url,
            env=config.env,
            timeout=30
        )


class MCPConnection:
    """
    MCP 连接基类
    """

    def __init__(self, config: MCPConnectionConfig):
        self.config = config
        self._connected = False
        self._server_capabilities: Optional[MCPCapabilities] = None
        self._request_id = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """建立连接"""
        raise NotImplementedError

    async def disconnect(self) -> None:
        """断开连接"""
        raise NotImplementedError

    async def send_request(
        self,
        method: MCPMessageType,
        params: Optional[Dict[str, Any]] = None
    ) -> MCPMessage:
        """发送请求"""
        raise NotImplementedError

    def _get_next_request_id(self) -> str:
        self._request_id += 1
        return f"req_{self._request_id}"


class StdioConnection(MCPConnection):
    """
    Stdio 连接

    通过启动子进程并使用标准输入输出进行通信。
    """

    def __init__(self, config: MCPConnectionConfig):
        super().__init__(config)
        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def connect(self) -> bool:
        """建立连接"""
        if self._connected:
            return True

        try:
            # 启动子进程
            cmd = [self.config.command] + self.config.args
            logger.info(f"[StdioConnection] 启动进程: {' '.join(cmd)}")

            # 创建子进程
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**dict(sys.environ), **self.config.env}
            )

            self._reader = self._process.stdout
            self._writer = self._process.stdin

            # 初始化连接
            init_result = await self._initialize()
            if init_result:
                self._connected = True
                logger.info(f"[StdioConnection] 连接成功: {self.config.name}")
                return True
            else:
                await self.disconnect()
                return False

        except Exception as e:
            logger.error(f"[StdioConnection] 连接失败: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except Exception as e:
                logger.warning(f"[StdioConnection] 终止进程失败: {e}")
                try:
                    self._process.kill()
                except:
                    pass

        self._process = None
        self._reader = None
        self._writer = None
        self._connected = False
        logger.info(f"[StdioConnection] 已断开: {self.config.name}")

    async def send_request(
        self,
        method: MCPMessageType,
        params: Optional[Dict[str, Any]] = None
    ) -> MCPMessage:
        """发送请求"""
        if not self._connected or not self._writer or not self._reader:
            return MCPMessage.error_response(
                request_id="",
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message="Not connected"
                )
            )

        request = MCPMessage.request(
            method=method,
            params=params,
            request_id=self._get_next_request_id()
        )

        try:
            # 发送请求
            request_json = request.to_json() + "\n"
            self._writer.write(request_json.encode())
            await self._writer.drain()

            logger.debug(f"[StdioConnection] 发送请求: {request_json.strip()}")

            # 读取响应
            response_line = await asyncio.wait_for(
                self._reader.readline(),
                timeout=self.config.timeout
            )

            if not response_line:
                raise Exception("Empty response")

            response_str = response_line.decode().strip()
            logger.debug(f"[StdioConnection] 收到响应: {response_str}")

            return MCPMessage.from_json(response_str)

        except asyncio.TimeoutError:
            logger.error(f"[StdioConnection] 请求超时")
            return MCPMessage.error_response(
                request_id=request.id or "",
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message="Request timeout"
                )
            )
        except Exception as e:
            logger.error(f"[StdioConnection] 请求失败: {e}")
            return MCPMessage.error_response(
                request_id=request.id or "",
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message=str(e)
                )
            )

    async def _initialize(self) -> bool:
        """初始化连接"""
        response = await self.send_request(
            method=MCPMessageType.INITIALIZE,
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test2langchain-mcp-client",
                    "version": "1.0.0"
                }
            }
        )

        if response.error:
            logger.error(f"[StdioConnection] 初始化失败: {response.error}")
            return False

        return True


class SSEConnection(MCPConnection):
    """
    SSE 连接

    通过 Server-Sent Events 连接远程服务器。
    """

    def __init__(self, config: MCPConnectionConfig):
        super().__init__(config)
        self._session = None

    async def connect(self) -> bool:
        """建立连接"""
        if self._connected:
            return True

        try:
            import aiohttp

            self._session = aiohttp.ClientSession()
            init_result = await self._initialize()

            if init_result:
                self._connected = True
                logger.info(f"[SSEConnection] 连接成功: {self.config.name}")
                return True
            else:
                await self.disconnect()
                return False

        except ImportError:
            logger.error("[SSEConnection] 需要 aiohttp 库")
            return False
        except Exception as e:
            logger.error(f"[SSEConnection] 连接失败: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._session:
            await self._session.close()
            self._session = None

        self._connected = False
        logger.info(f"[SSEConnection] 已断开: {self.config.name}")

    async def send_request(
        self,
        method: MCPMessageType,
        params: Optional[Dict[str, Any]] = None
    ) -> MCPMessage:
        """发送请求"""
        if not self._connected or not self._session:
            return MCPMessage.error_response(
                request_id="",
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message="Not connected"
                )
            )

        request = MCPMessage.request(
            method=method,
            params=params,
            request_id=self._get_next_request_id()
        )

        try:
            async with self._session.post(
                f"{self.config.url}/message",
                json=json.loads(request.to_json()),
                timeout=self.config.timeout
            ) as response:
                response_data = await response.json()
                return MCPMessage.from_json(json.dumps(response_data))

        except Exception as e:
            logger.error(f"[SSEConnection] 请求失败: {e}")
            return MCPMessage.error_response(
                request_id=request.id or "",
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message=str(e)
                )
            )

    async def _initialize(self) -> bool:
        """初始化连接"""
        response = await self.send_request(
            method=MCPMessageType.INITIALIZE,
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test2langchain-mcp-client",
                    "version": "1.0.0"
                }
            }
        )

        return not response.error


class MCPClient:
    """
    MCP 客户端

    连接到 MCP 服务器并调用工具。
    """

    def __init__(self):
        self._connections: Dict[str, MCPConnection] = {}
        self._tools_cache: Dict[str, List[MCPToolDefinition]] = {}
        self._lock = asyncio.Lock()
        logger.info("[MCPClient] 初始化完成")

    async def connect_to_server(
        self,
        config: MCPConnectionConfig
    ) -> bool:
        """
        连接到 MCP 服务器

        Args:
            config: 连接配置

        Returns:
            是否连接成功
        """
        async with self._lock:
            if config.name in self._connections:
                logger.warning(f"[MCPClient] 已存在连接: {config.name}")
                return True

            if config.transport == "stdio":
                connection = StdioConnection(config)
            elif config.transport == "sse":
                connection = SSEConnection(config)
            else:
                logger.error(f"[MCPClient] 不支持的传输方式: {config.transport}")
                return False

            success = await connection.connect()
            if success:
                self._connections[config.name] = connection
                # 缓存工具列表
                await self._refresh_tools_cache(config.name)
                return True

            return False

    async def disconnect(self, server_name: Optional[str] = None) -> None:
        """
        断开连接

        Args:
            server_name: 服务器名称，为 None 则断开所有连接
        """
        async with self._lock:
            if server_name:
                if server_name in self._connections:
                    await self._connections[server_name].disconnect()
                    del self._connections[server_name]
                    if server_name in self._tools_cache:
                        del self._tools_cache[server_name]
            else:
                for conn in self._connections.values():
                    await conn.disconnect()
                self._connections.clear()
                self._tools_cache.clear()

    async def list_tools(
        self,
        server_name: Optional[str] = None
    ) -> Dict[str, List[MCPToolDefinition]]:
        """
        列出可用工具

        Args:
            server_name: 服务器名称，为 None 则返回所有服务器的工具

        Returns:
            服务器名称到工具列表的映射
        """
        if server_name:
            if server_name in self._tools_cache:
                return {server_name: self._tools_cache[server_name]}
            return {server_name: []}

        return dict(self._tools_cache)

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> MCPToolResult:
        """
        调用工具

        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用结果
        """
        connection = self._connections.get(server_name)
        if not connection:
            return MCPToolResult.error(
                call_id="",
                error_message=f"Not connected to server: {server_name}"
            )

        response = await connection.send_request(
            method=MCPMessageType.CALL_TOOL,
            params={
                "name": tool_name,
                "arguments": arguments
            }
        )

        if response.error:
            return MCPToolResult.error(
                call_id="",
                error_message=response.error.message
            )

        result_data = response.result or {}
        return MCPToolResult(
            call_id=result_data.get("call_id", ""),
            content=result_data.get("content", []),
            is_error=result_data.get("isError", False),
            error_message=result_data.get("errorMessage")
        )

    async def _refresh_tools_cache(self, server_name: str) -> None:
        """刷新工具缓存"""
        connection = self._connections.get(server_name)
        if not connection:
            return

        response = await connection.send_request(
            method=MCPMessageType.LIST_TOOLS
        )

        if response.error or not response.result:
            logger.warning(f"[MCPClient] 获取工具列表失败: {server_name}")
            return

        tools_data = response.result.get("tools", [])
        tools = []
        for tool_data in tools_data:
            from mcp.protocol import MCPToolInputSchema
            tool = MCPToolDefinition(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                input_schema=MCPToolInputSchema(
                    type=tool_data.get("inputSchema", {}).get("type", "object"),
                    properties=tool_data.get("inputSchema", {}).get("properties", {}),
                    required=tool_data.get("inputSchema", {}).get("required", [])
                )
            )
            tools.append(tool)

        self._tools_cache[server_name] = tools
        logger.info(f"[MCPClient] 缓存工具: {server_name}, 数量: {len(tools)}")

    @property
    def connected_servers(self) -> List[str]:
        """已连接的服务器列表"""
        return list(self._connections.keys())


# 全局客户端实例
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """获取 MCP 客户端实例（单例）"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client
