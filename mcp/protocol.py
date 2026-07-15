"""
MCP Protocol 定义

实现 Model Context Protocol 的消息格式和协议处理。

参考规范: https://modelcontextprotocol.io/
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field


class MCPMessageType(str, Enum):
    """MCP 消息类型"""
    # 请求类型
    INITIALIZE = "initialize"
    LIST_TOOLS = "tools/list"
    CALL_TOOL = "tools/call"
    LIST_RESOURCES = "resources/list"
    READ_RESOURCE = "resources/read"
    LIST_PROMPTS = "prompts/list"
    GET_PROMPT = "prompts/get"

    # 响应类型
    RESULT = "result"
    ERROR = "error"

    # 通知类型
    NOTIFICATION = "notification"
    LOGGING = "logging/log"
    PROGRESS = "progress"


class MCPErrorCode(int, Enum):
    """MCP 错误代码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # 自定义错误
    TOOL_NOT_FOUND = -32001
    TOOL_EXECUTION_ERROR = -32002
    RESOURCE_NOT_FOUND = -32003
    RESOURCE_ACCESS_ERROR = -32004


@dataclass
class MCPToolInputSchema:
    """工具输入参数 Schema"""
    type: str = "object"
    properties: Dict[str, Any] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "properties": self.properties,
            "required": self.required
        }


@dataclass
class MCPToolDefinition:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: MCPToolInputSchema

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema.to_dict()
        }


@dataclass
class MCPToolCall:
    """MCP 工具调用请求"""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id
        }


@dataclass
class MCPToolResult:
    """MCP 工具调用结果"""
    call_id: str
    content: List[Dict[str, Any]]
    is_error: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "call_id": self.call_id,
            "content": self.content
        }
        if self.is_error:
            result["isError"] = True
            if self.error_message:
                result["errorMessage"] = self.error_message
        return result

    @classmethod
    def success(cls, call_id: str, content: Union[str, Dict, List]) -> "MCPToolResult":
        """创建成功结果"""
        if isinstance(content, str):
            content_list = [{"type": "text", "text": content}]
        elif isinstance(content, dict):
            content_list = [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}]
        elif isinstance(content, list):
            content_list = content
        else:
            content_list = [{"type": "text", "text": str(content)}]

        return cls(call_id=call_id, content=content_list, is_error=False)

    @classmethod
    def error(cls, call_id: str, error_message: str) -> "MCPToolResult":
        """创建错误结果"""
        return cls(
            call_id=call_id,
            content=[{"type": "text", "text": error_message}],
            is_error=True,
            error_message=error_message
        )


@dataclass
class MCPError:
    """MCP 错误响应"""
    code: MCPErrorCode
    message: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.code.value,
            "message": self.message
        }
        if self.data:
            result["data"] = self.data
        return result


@dataclass
class MCPMessage:
    """MCP 消息基类"""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[MCPMessageType] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[MCPError] = None

    def to_json(self) -> str:
        """序列化为 JSON"""
        data = {"jsonrpc": self.jsonrpc}

        if self.id:
            data["id"] = self.id
        if self.method:
            data["method"] = self.method.value
        if self.params:
            data["params"] = self.params
        if self.result is not None:
            data["result"] = self.result
        if self.error:
            data["error"] = self.error.to_dict()

        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "MCPMessage":
        """从 JSON 反序列化"""
        data = json.loads(json_str)

        error = None
        if "error" in data:
            error = MCPError(
                code=MCPErrorCode(data["error"]["code"]),
                message=data["error"]["message"],
                data=data["error"].get("data")
            )

        method = None
        if "method" in data:
            try:
                method = MCPMessageType(data["method"])
            except ValueError:
                pass

        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=method,
            params=data.get("params"),
            result=data.get("result"),
            error=error
        )

    @classmethod
    def request(
        cls,
        method: MCPMessageType,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> "MCPMessage":
        """创建请求消息"""
        return cls(
            id=request_id or str(uuid.uuid4()),
            method=method,
            params=params
        )

    @classmethod
    def response(
        cls,
        request_id: str,
        result: Any
    ) -> "MCPMessage":
        """创建响应消息"""
        return cls(
            id=request_id,
            result=result
        )

    @classmethod
    def error_response(
        cls,
        request_id: str,
        error: MCPError
    ) -> "MCPMessage":
        """创建错误响应"""
        return cls(
            id=request_id,
            error=error
        )


@dataclass
class MCPResource:
    """MCP 资源定义"""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "uri": self.uri,
            "name": self.name
        }
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type
        return result


@dataclass
class MCPPrompt:
    """MCP Prompt 定义"""
    name: str
    description: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments
        }


@dataclass
class MCPCapabilities:
    """MCP 服务器能力声明"""
    tools: bool = False
    resources: bool = False
    prompts: bool = False
    logging: bool = False

    def to_dict(self) -> Dict[str, Any]:
        capabilities = {}
        if self.tools:
            capabilities["tools"] = {}
        if self.resources:
            capabilities["resources"] = {}
        if self.prompts:
            capabilities["prompts"] = {}
        if self.logging:
            capabilities["logging"] = {}
        return capabilities


@dataclass
class MCPInitializeResult:
    """初始化响应结果"""
    protocol_version: str = "2024-11-05"
    capabilities: MCPCapabilities = field(default_factory=MCPCapabilities)
    server_info: Dict[str, str] = field(default_factory=lambda: {
        "name": "test2langchain-mcp-server",
        "version": "1.0.0"
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": self.capabilities.to_dict(),
            "serverInfo": self.server_info
        }
