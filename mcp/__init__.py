"""
MCP (Model Context Protocol) 模块

提供 Model Context Protocol 支持，允许 AI 模型连接外部工具和数据源。

核心组件：
- MCPClient: 连接 MCP 服务器的客户端
- MCPServer: 本地 MCP 服务器实现
- MCPToolAdapter: 工具适配器，将现有工具包装为 MCP 工具
- MCPProtocol: 协议定义和消息处理
"""

from mcp.client import MCPClient, MCPConnectionConfig
from mcp.server import MCPServer, MCPServerConfig
from mcp.tools import MCPToolAdapter, MCPToolRegistry
from mcp.protocol import (
    MCPMessage,
    MCPMessageType,
    MCPToolCall,
    MCPToolResult,
    MCPError
)
from mcp.config import MCPSettings, get_mcp_settings

__all__ = [
    # Client
    "MCPClient",
    "MCPConnectionConfig",
    # Server
    "MCPServer",
    "MCPServerConfig",
    # Tools
    "MCPToolAdapter",
    "MCPToolRegistry",
    # Protocol
    "MCPMessage",
    "MCPMessageType",
    "MCPToolCall",
    "MCPToolResult",
    "MCPError",
    # Config
    "MCPSettings",
    "get_mcp_settings",
]

__version__ = "1.0.0"
