"""
日志管理模块
使用loguru提供结构化日志记录，支持多种输出格式和级别
"""

import io
import sys
import os
from typing import Optional
from loguru import logger


def _safe_console_stream(stream):
    """Return a console stream that will not raise on unsupported characters."""
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(errors="replace")
            return stream
        except Exception:
            pass

    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return stream

    encoding = getattr(stream, "encoding", None) or "utf-8"
    return io.TextIOWrapper(
        buffer,
        encoding=encoding,
        errors="replace",
        line_buffering=True,
    )


class LoggerManager:
    """
    日志管理器
    
    提供统一的日志配置和管理功能
    支持文件输出、控制台输出和结构化日志
    """
    
    _initialized = False
    
    @classmethod
    def initialize(cls, log_dir: Optional[str] = None) -> None:
        """
        初始化日志配置
        
        Args:
            log_dir: 日志文件目录，默认为项目根目录下的logs文件夹
        """
        if cls._initialized:
            return
        
        # 移除默认的日志处理器
        logger.remove()
        
        # 设置日志目录
        if log_dir is None:
            project_root = os.path.dirname(os.path.dirname(__file__))
            log_dir = os.path.join(project_root, "logs")
        
        # 确保日志目录存在
        os.makedirs(log_dir, exist_ok=True)
        
        # 获取日志级别（延迟导入settings避免循环依赖）
        try:
            from config.settings import settings
            log_level = settings.app.log_level
        except Exception:
            log_level = "INFO"  # 默认级别
        
        # 控制台输出配置
        logger.add(
            _safe_console_stream(sys.stdout),
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level>",
            level=log_level,
            colorize=True,
            backtrace=True,
            diagnose=True
        )
        
        # 应用日志文件配置
        logger.add(
            os.path.join(log_dir, "app_{time:YYYY-MM-DD}.log"),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation="00:00",  # 每天轮转
            retention="30 days",  # 保留30天
            compression="zip",  # 压缩旧日志
            encoding="utf-8",
            backtrace=True,
            diagnose=True
        )
        
        # 错误日志文件配置
        logger.add(
            os.path.join(log_dir, "error_{time:YYYY-MM-DD}.log"),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="ERROR",
            rotation="00:00",
            retention="90 days",  # 错误日志保留更长时间
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True
        )
        
        # API调用日志文件配置
        logger.add(
            os.path.join(log_dir, "api_{time:YYYY-MM-DD}.log"),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[api_name]} | {message}",
            level="INFO",
            rotation="00:00",
            retention="7 days",
            compression="zip",
            encoding="utf-8",
            filter=lambda record: "api_name" in record["extra"]
        )
        
        cls._initialized = True
        logger.info(f"日志系统初始化完成，日志级别: {log_level}")
    
    @classmethod
    def get_logger(cls, name: str = None):
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称
            
        Returns:
            logger: 配置好的日志记录器
        """
        if not cls._initialized:
            cls.initialize()
        
        if name:
            return logger.bind(name=name)
        return logger


def log_api_call(api_name: str, method: str, url: str, status_code: Optional[int] = None, 
                 response_time: Optional[float] = None, error: Optional[str] = None):
    """
    记录API调用日志
    
    Args:
        api_name: API名称
        method: HTTP方法
        url: 请求URL
        status_code: 响应状态码
        response_time: 响应时间(毫秒)
        error: 错误信息
    """
    api_logger = logger.bind(api_name=api_name)
    
    log_message = f"{method} {url}"
    if status_code:
        log_message += f" - {status_code}"
    if response_time:
        log_message += f" - {response_time:.2f}ms"
    if error:
        log_message += f" - ERROR: {error}"
        api_logger.error(log_message)
    else:
        api_logger.info(log_message)


def log_tool_execution(tool_name: str, input_data: dict, output_data: Optional[dict] = None, 
                      execution_time: Optional[float] = None, error: Optional[str] = None):
    """
    记录工具执行日志
    
    Args:
        tool_name: 工具名称
        input_data: 输入数据
        output_data: 输出数据
        execution_time: 执行时间(毫秒)
        error: 错误信息
    """
    tool_logger = logger.bind(tool_name=tool_name)
    
    log_message = f"工具执行: {tool_name}"
    if execution_time:
        log_message += f" - {execution_time:.2f}ms"
    
    if error:
        tool_logger.error(f"{log_message} - ERROR: {error}", input=input_data)
    else:
        tool_logger.info(f"{log_message} - SUCCESS", input=input_data, output=output_data)


def log_conversation(session_id: str, user_input: str, assistant_response: str, 
                    tools_used: Optional[list] = None):
    """
    记录对话日志
    
    Args:
        session_id: 会话ID
        user_input: 用户输入
        assistant_response: 助手响应
        tools_used: 使用的工具列表
    """
    conversation_logger = logger.bind(session_id=session_id)
    
    conversation_logger.info(
        "对话记录",
        user_input=user_input,
        assistant_response=assistant_response,
        tools_used=tools_used or []
    )


# 初始化日志管理器
LoggerManager.initialize()

# 导出常用的日志记录器
app_logger = LoggerManager.get_logger("app")
api_logger = LoggerManager.get_logger("api")
tool_logger = LoggerManager.get_logger("tool")
