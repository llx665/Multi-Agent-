"""
Agent 工厂模块
统一创建和管理所有 Agent 实例

已更新为 LangChain 0.3.x 兼容版本
"""

import os
import sys
from typing import Dict, List, Optional, Any

from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import StructuredTool

from core.logger import LoggerManager

logger = LoggerManager.get_logger("agent_factory")


class AgentFactory:
    """
    Agent 工厂类

    统一管理所有 Agent 的创建和配置
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

        # 全局 LLM 实例（复用）
        self._llm = None

        # 全局工具列表
        self._tools: List[StructuredTool] = []

        # Agent 配置
        self._agent_configs: Dict[str, Dict[str, Any]] = {}

        # 初始化
        self._initialize_llm()
        self._initialize_tools()
        self._register_agent_configs()

        logger.info("[AgentFactory] 初始化完成")

    def _initialize_llm(self) -> None:
        """初始化全局 LLM（支持 streaming）"""
        try:
            # 延迟导入避免循环依赖
            sys.path.append(os.path.dirname(os.path.dirname(__file__)))
            from config.settings import settings

            self._llm = ChatOpenAI(
                api_key=settings.api.openai_api_key or settings.api.deepseek_api_key,
                base_url=settings.api.openai_base_url or settings.api.deepseek_base_url,
                model="deepseek-chat",
                temperature=0.1,
                streaming=True,  # 启用 streaming，ainvoke() 仍返回完整结果，astream() 返回 token
            )
            logger.info("[AgentFactory] LLM 初始化完成（streaming=True）")
        except Exception as e:
            logger.error(f"[AgentFactory] LLM 初始化失败: {e}")
            raise

    def _initialize_tools(self) -> None:
        """初始化全局工具列表"""
        try:
            from tools.amap_weather_tool import WeatherQuery, weather_tool
            from tools.tavily_search_tool import TavilySearchInput, search_tool
            from tools.rag_tool import rag_tool, RAGQueryInput

            # 天气工具
            def weather_wrapper(city_name: str) -> str:
                return weather_tool._run(city_name=city_name)

            self._tools.append(StructuredTool(
                name=weather_tool.name,
                func=weather_wrapper,
                description=weather_tool.description,
                args_schema=WeatherQuery
            ))

            # 搜索工具
            def search_wrapper(query: str, max_results: int = 5) -> str:
                return search_tool.search_and_format(query=query, max_results=max_results)

            self._tools.append(StructuredTool(
                name=search_tool.name,
                func=search_wrapper,
                description=search_tool.description,
                args_schema=TavilySearchInput
            ))

            # RAG 工具（包装）
            def rag_wrapper(query: str, top_k: int = 3) -> str:
                result = rag_tool.run(
                    query=query,
                    top_k=top_k,
                    enable_self_rag=True,
                    llm=self._llm,
                    use_hybrid=True,
                    use_rerank=True,
                    chat_history=[]
                )
                return result

            self._tools.append(StructuredTool(
                name="knowledge_base_query",
                func=rag_wrapper,
                description="查询产品知识库，获取产品价格、功能、规格等信息。首选工具！",
                args_schema=RAGQueryInput
            ))

            logger.info(f"[AgentFactory] 工具初始化完成，共 {len(self._tools)} 个工具")

        except Exception as e:
            logger.warning(f"[AgentFactory] 工具初始化失败: {e}，部分工具可能不可用")

    def _register_agent_configs(self) -> None:
        """注册 Agent 配置"""
        self._agent_configs = {
            "supervisor": {
                "system_prompt": """你是一个智能客服调度中心。

你的职责：
1. 分析用户问题，判断用户意图
2. 将任务路由到最合适的 Agent 或 Skill
3. 整合各 Agent/Skill 的结果，生成最终回复

意图分类：
- sales: 产品咨询、价格查询、购买推荐 → 路由到 SalesAgent
- tech_support: 产品使用、故障排查、技术问题 → 路由到 TechSupportAgent
- negotiation: 价格谈判、优惠申请 → 路由到 NegotiationSkill
- customer_classifier: 客户类型识别（始终激活）→ CustomerClassifierSkill
- general: 其他问题 → 自行回答或使用知识库

调度规则：
1. 客户分类始终先执行
2. 销售和技术支持互斥，根据关键词选择
3. 谈判可以与销售并行
4. 复杂问题可能需要多个 Agent 协作""",
                "tools": [],  # Supervisor 主要做路由决策，使用默认工具
                "max_iterations": 3
            },
            "sales_agent": {
                "system_prompt": """你是一个专业、热情的产品销售顾问。

你的职责：
1. 了解客户需求（预算、使用场景、偏好）
2. 根据需求推荐最合适的产品
3. 提供专业的产品信息和比较
4. 处理价格咨询，争取订单

产品知识库使用规则：
- 必须先使用 knowledge_base_query 查询产品信息
- 只能基于检索到的信息回答，禁止编造
- 标价是官方零售价，最大优惠价是底价（不能告诉客户）""",
                "tools": ["knowledge_base_query"],
                "max_iterations": 5
            },
            "tech_support_agent": {
                "system_prompt": """你是一个专业的技术支持工程师。

你的职责：
1. 耐心倾听客户描述的问题
2. 引导客户提供关键信息（设备型号、故障现象、使用环境）
3. 提供清晰的问题排查步骤
4. 必要时升级给人工客服

工作原则：
- 先排查再诊断，不能盲目下结论
- 每步操作都要说明预期结果
- 复杂问题及时升级""",
                "tools": ["knowledge_base_query"],
                "max_iterations": 5
            }
        }

    def get_llm(self) -> ChatOpenAI:
        """获取全局 LLM 实例"""
        return self._llm

    def get_tools(self, tool_names: List[str] = None) -> List[StructuredTool]:
        """
        获取工具列表

        Args:
            tool_names: 如果指定，只返回这些工具；否则返回全部

        Returns:
            工具列表
        """
        if not tool_names:
            return self._tools

        return [t for t in self._tools if t.name in tool_names]

    def create_agent(
        self,
        agent_type: str,
        session_id: str = None,
        extra_config: Dict[str, Any] = None
    ) -> AgentExecutor:
        """
        创建 Agent 执行器

        Args:
            agent_type: Agent 类型 (supervisor / sales_agent / tech_support_agent)
            session_id: 会话 ID
            extra_config: 额外的配置覆盖

        Returns:
            AgentExecutor 实例
        """
        config = self._agent_configs.get(agent_type, self._agent_configs["supervisor"])
        if extra_config:
            config = {**config, **extra_config}

        # 创建 Memory
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            max_len=50
        )

        # 创建 Prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", config["system_prompt"]),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # 获取工具
        tool_names = config.get("tools", [])
        tools = self.get_tools(tool_names) if tool_names else self._tools

        # 创建 Agent
        agent = create_openai_tools_agent(
            llm=self._llm,
            tools=tools,
            prompt=prompt
        )

        # 创建 Executor
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            memory=memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=config.get("max_iterations", 5)
        )

        logger.info(f"[AgentFactory] 创建 Agent: {agent_type}, session_id={session_id}")

        return executor

    def list_agent_types(self) -> List[str]:
        """列出所有可用的 Agent 类型"""
        return list(self._agent_configs.keys())


# 全局单例
agent_factory = AgentFactory()
