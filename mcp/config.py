"""
MCP 配置管理

提供 MCP 客户端和服务器的配置管理。
"""

import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class MCPServerConnectionConfig(BaseModel):
    """MCP 服务器连接配置"""
    name: str = Field(..., description="服务器名称")
    transport: str = Field(default="stdio", description="传输方式: stdio, sse, websocket")
    command: Optional[str] = Field(default=None, description="启动命令(stdio模式)")
    args: List[str] = Field(default_factory=list, description="命令参数")
    url: Optional[str] = Field(default=None, description="服务器URL(SSE/WebSocket模式)")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    enabled: bool = Field(default=True, description="是否启用")


class MCPSettings(BaseSettings):
    """MCP 全局配置"""
    # 服务器配置
    mcp_enabled: bool = Field(default=True, description="是否启用 MCP")
    mcp_server_name: str = Field(default="test2langchain-mcp", description="MCP 服务器名称")
    mcp_server_version: str = Field(default="1.0.0", description="MCP 服务器版本")

    # 连接配置
    mcp_connection_timeout: int = Field(default=30, description="连接超时(秒)")
    mcp_request_timeout: int = Field(default=60, description="请求超时(秒)")

    # 外部 MCP 服务器
    mcp_external_servers: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="外部 MCP 服务器配置列表"
    )

    # 工具配置
    mcp_max_concurrent_calls: int = Field(default=10, description="最大并发工具调用数")
    mcp_tool_timeout: int = Field(default=300, description="工具执行超时(秒)")

    # 日志配置
    mcp_log_level: str = Field(default="INFO", description="MCP 日志级别")

    class Config:
        env_prefix = "MCP_"
        case_sensitive = False

    def get_external_server_configs(self) -> List[MCPServerConnectionConfig]:
        """获取外部服务器配置列表"""
        configs = []
        for server_data in self.mcp_external_servers:
            try:
                config = MCPServerConnectionConfig(**server_data)
                if config.enabled:
                    configs.append(config)
            except Exception as e:
                print(f"[MCP Config] 解析服务器配置失败: {e}")
        return configs


# 全局配置实例
_mcp_settings: Optional[MCPSettings] = None


def get_mcp_settings() -> MCPSettings:
    """获取 MCP 配置实例（单例）"""
    global _mcp_settings
    if _mcp_settings is None:
        _mcp_settings = MCPSettings()
    return _mcp_settings


# 预定义的常用 MCP 服务器配置
PREDEFINED_MCP_SERVERS = {
    "filesystem": {
        "name": "filesystem",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
        "description": "文件系统访问服务器"
    },
    "memory": {
        "name": "memory",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "description": "内存存储服务器"
    },
    "brave-search": {
        "name": "brave-search",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": ""},
        "description": "Brave 搜索服务器"
    },
    "github": {
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": ""},
        "description": "GitHub 集成服务器"
    },
    "slack": {
        "name": "slack",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": ""},
        "description": "Slack 集成服务器"
    }
}


def get_predefined_server_config(name: str, **kwargs) -> MCPServerConnectionConfig:
    """
    获取预定义的 MCP 服务器配置

    Args:
        name: 服务器名称 (filesystem, memory, brave-search, github, slack)
        **kwargs: 额外配置参数覆盖

    Returns:
        MCPServerConnectionConfig
    """
    if name not in PREDEFINED_MCP_SERVERS:
        raise ValueError(f"未知的预定义服务器: {name}. 可用: {list(PREDEFINED_MCP_SERVERS.keys())}")

    config_data = PREDEFINED_MCP_SERVERS[name].copy()
    config_data.update(kwargs)
    return MCPServerConnectionConfig(**config_data)
