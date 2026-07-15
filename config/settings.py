"""
配置管理模块
使用Pydantic进行配置验证和类型检查，符合企业级开发规范
"""

import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 新增：Milvus配置类
class VectorDBSettings(BaseSettings):
    """Milvus Lite向量数据库配置（嵌入式）"""
    vector_db_collection_name: str = Field(default="support_agent_rag", description="默认集合名称")
    vector_db_dimension: int = Field(default=768, description="向量维度（匹配text2vec-base-chinese模型768维）")
    vector_db_index_type: str = Field(default="IVF_FLAT", description="索引类型（平衡检索速度/精度）")
    vector_db_metric_type: str = Field(default="L2", description="距离计算方式")
    vector_db_data_path: str = Field(default="./milvus_data", description="Milvus Lite数据存储路径")

    class Config:
        env_prefix = "RAG_"
        case_sensitive = False

# 新增：RAG配置类
class RAGSettings(BaseSettings):
    """CRAG/Self-RAG配置"""
    # 嵌入模型配置 - 已更新为中文优化模型
    embedding_model_name: str = Field(default="shibing624/text2vec-base-chinese", description="向量嵌入模型（中文优化）")
    # 文档分块配置
    chunk_size: int = Field(default=500, description="文档分块大小（字符数）")
    chunk_overlap: int = Field(default=50, description="分块重叠长度（保证上下文连续）")
    # Self-RAG决策阈值
    self_rag_retrieval_threshold: float = Field(default=0.7, description="检索置信度阈值")
    self_rag_reflection_threshold: float = Field(default=0.8, description="回答充分性阈值")
    # CRAG实时更新配置
    crag_refresh_interval: int = Field(default=3600, description="知识库刷新间隔（秒）")
    crag_data_sources: List[str] = Field(default_factory=lambda: ["data/docs"], description="CRAG数据源路径/URL")
    
    class Config:
        env_prefix = ""
        case_sensitive = False
    
    def get_absolute_data_paths(self) -> List[str]:
        """获取绝对路径形式的数据源路径"""
        project_root = os.path.dirname(os.path.dirname(__file__))
        return [os.path.join(project_root, p) for p in self.crag_data_sources]

class APISettings(BaseSettings):
    """API相关配置"""

    # OpenAI配置
    openai_api_key: str = Field(default="", description="OpenAI API密钥")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API基础URL")

    # 高德地图API配置
    amap_api_key: str = Field(default="", description="高德地图API密钥")
    amap_base_url: str = Field(default="https://restapi.amap.com/v3", description="高德地图API基础URL")

    # Tavily搜索API配置
    tavily_api_key: str = Field(default="", description="Tavily搜索API密钥")

    # DeepSeek API配置
    deepseek_api_key: str = Field(default="", description="DeepSeek API密钥")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", description="DeepSeek API基础URL")
    deepseek_model: str = Field(default="deepseek-chat", description="DeepSeek模型名称")

    class Config:
        env_prefix = ""
        case_sensitive = False

    # 兼容旧代码的扁平属性
    @property
    def api_key(self) -> str:
        """兼容旧代码：返回openai_api_key"""
        return self.openai_api_key



class DatabaseSettings(BaseSettings):
    """鏁版嵁搴撴璁℃帴鍙ｆ鏌?"""

    database_url: str = Field(default="sqlite:///data/auth/app.db", description="鏁版嵁搴撴連鍙ｇ洃鍚?URL锛岄粯璁や娇鐢ㄥ唴缃繚瀛樼殑SQLite")
    database_echo: bool = Field(default=False, description="鏄惁鎵撳嵃SQL璋冩暣鏃ュ織")

    class Config:
        env_prefix = ""
        case_sensitive = False


class RedisSettings(BaseSettings):
    """Redis缓存配置"""
    
    redis_host: str = Field(default="localhost", description="Redis主机地址")
    redis_port: int = Field(default=6379, description="Redis端口")
    redis_db: int = Field(default=0, description="Redis数据库编号")
    redis_password: Optional[str] = Field(default=None, description="Redis密码")
    
    @validator('redis_port')
    def validate_port(cls, v):
        """验证端口范围"""
        if not 1 <= v <= 65535:
            raise ValueError("端口号必须在1-65535范围内")
        return v
    
    class Config:
        env_prefix = ""
        case_sensitive = False


class AppSettings(BaseSettings):
    """应用程序配置"""
    
    app_name: str = Field(default="MultiTaskQAAssistant", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    log_level: str = Field(default="INFO", description="日志级别")
    max_conversation_history: int = Field(default=50, description="最大对话历史记录数")
    cache_ttl: int = Field(default=3600, description="缓存过期时间(秒)")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """验证日志级别"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"日志级别必须是以下之一: {valid_levels}")
        return v.upper()
    
    @validator('max_conversation_history', 'cache_ttl')
    def validate_positive_int(cls, v):
        """验证正整数"""
        if v <= 0:
            raise ValueError("值必须大于0")
        return v
    
    class Config:
        env_prefix = ""
        case_sensitive = False


class Settings:
    """
    全局配置管理器

    采用单例模式，确保配置的一致性和性能
    提供统一的配置访问接口
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self.__class__._initialized:
            try:
                self.api = APISettings()
                self.redis = RedisSettings()
                self.database = DatabaseSettings()
                self.app = AppSettings()
                self.vector_db = VectorDBSettings()
                self.rag = RAGSettings()
                self.__class__._initialized = True
            except Exception as e:
                raise RuntimeError(f"配置初始化失败: {str(e)}")

    # ============ 兼容旧代码的扁平属性 ============

    @property
    def app_name(self) -> str:
        return self.app.app_name

    @property
    def app_version(self) -> str:
        return self.app.app_version

    @property
    def log_level(self) -> str:
        return self.app.log_level

    @property
    def max_conversation_history(self) -> int:
        return self.app.max_conversation_history

    @property
    def cache_ttl(self) -> int:
        return self.app.cache_ttl

    @property
    def debug(self) -> bool:
        return self.app.log_level == "DEBUG"

    # API 相关（支持扁平和嵌套两种访问方式）
    @property
    def deepseek_api_key(self) -> str:
        return self.api.deepseek_api_key

    @property
    def deepseek_base_url(self) -> str:
        return self.api.deepseek_base_url

    @property
    def deepseek_model(self) -> str:
        return self.api.deepseek_model

    @property
    def openai_api_key(self) -> str:
        return self.api.openai_api_key

    @property
    def openai_base_url(self) -> str:
        return self.api.openai_base_url

    @property
    def amap_api_key(self) -> str:
        return self.api.amap_api_key

    @property
    def amap_base_url(self) -> str:
        return self.api.amap_base_url

    @property
    def tavily_api_key(self) -> str:
        return self.api.tavily_api_key

    # Redis 相关
    @property
    def redis_host(self) -> str:
        return self.redis.redis_host

    @property
    def redis_port(self) -> int:
        return self.redis.redis_port

    @property
    def redis_db(self) -> int:
        return self.redis.redis_db

    @property
    def redis_password(self) -> Optional[str]:
        return self.redis.redis_password

    # 数据库相关
    @property
    def database_url(self) -> str:
        return self.database.database_url

    @property
    def database_echo(self) -> bool:
        return bool(self.database.database_echo)

    # 向量数据库相关
    @property
    def milvus_host(self) -> str:
        return "localhost"  # 向后兼容

    @property
    def milvus_port(self) -> int:
        return 19530  # 向后兼容

    @property
    def milvus_collection(self) -> str:
        return self.vector_db.vector_db_collection_name

    @property
    def milvus_collection_name(self) -> str:
        return self.vector_db.vector_db_collection_name

    @property
    def milvus_dimension(self) -> int:
        return self.vector_db.vector_db_dimension

    @property
    def milvus_index_type(self) -> str:
        return self.vector_db.vector_db_index_type

    @property
    def milvus_metric_type(self) -> str:
        return self.vector_db.vector_db_metric_type

    # RAG 相关
    @property
    def rag_embedding_model_name(self) -> str:
        return self.rag.embedding_model_name

    @property
    def rag_chunk_size(self) -> int:
        return self.rag.chunk_size

    @property
    def rag_chunk_overlap(self) -> int:
        return self.rag.chunk_overlap

    @property
    def rag_self_rag_retrieval_threshold(self) -> float:
        return self.rag.self_rag_retrieval_threshold

    @property
    def rag_self_rag_reflection_threshold(self) -> float:
        return self.rag.self_rag_reflection_threshold

    @property
    def rag_crag_refresh_interval(self) -> int:
        return self.rag.crag_refresh_interval

    @property
    def rag_crag_data_sources(self) -> str:
        return self.rag.crag_data_sources[0] if self.rag.crag_data_sources else "data/docs"
    
    def get_city_data_path(self) -> str:
        """获取城市数据文件路径"""
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "China-City-List-latest.csv")
    
    def validate_all(self) -> bool:
        """验证所有配置"""
        try:
            # 检查必需的API密钥
            warnings = []
            if not self.api.openai_api_key:
                warnings.append("OpenAI API密钥未配置")

            if not self.api.amap_api_key:
                warnings.append("高德地图API密钥未配置")

            if not self.api.deepseek_api_key:
                warnings.append("DeepSeek API密钥未配置")

            if not self.api.tavily_api_key:
                warnings.append("Tavily API密钥未配置，搜索功能可能无法使用")

            if warnings:
                for w in warnings:
                    print(f"[WARN] {w}")
                return False

            print("[OK] 配置验证通过")
            return True

        except Exception as e:
            print(f"[ERR] 配置验证失败: {str(e)}")
            return False


# 全局配置实例
settings = Settings()
