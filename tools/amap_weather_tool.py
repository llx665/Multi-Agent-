"""
高德地图天气查询工具

提供基于城市名的天气查询功能，支持城市名到adcode的映射
"""

import time
import requests
from typing import Optional, Dict, Any
from langchain.tools import BaseTool
import sys
import os
from loguru import logger

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 简化日志记录函数
def log_api_call(api_name: str, method: str, url: str, status_code: int = None, 
                 response_time: float = None, error: str = None):
    """记录API调用日志"""
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

def log_tool_execution(tool_name: str, input_data: dict, output_data: dict = None, 
                      execution_time: float = None, error: str = None):
    """记录工具执行日志"""
    tool_logger = logger.bind(tool_name=tool_name)
    
    log_message = f"工具执行: {tool_name}"
    if execution_time:
        log_message += f" - {execution_time:.2f}ms"
    
    if error:
        tool_logger.error(f"{log_message} - ERROR: {error}", input=input_data)
    else:
        tool_logger.info(f"{log_message} - SUCCESS", input=input_data, output=output_data)

app_logger = logger.bind(name="app")
from config.settings import settings
from pydantic.v1 import BaseModel, Field

# 直接定义WeatherQuery类
class WeatherQuery(BaseModel):
    """天气查询工具"""
    
    city_name: str = Field(
        ..., 
        description="要查询天气的城市名称，例如：北京、上海、广州等"
    )
    
    class Config:
        schema_extra = {
            "examples": [
                {"city_name": "北京"},
                {"city_name": "上海"},
                {"city_name": "广州"}
            ]
        }


class AmapWeatherTool(BaseTool):
    """
    高德地图天气查询工具
    
    根据城市名查询天气信息，支持城市名到adcode的映射
    """
    
    name: str = "amap_weather"
    description: str = "根据城市名称查询天气信息，返回详细的天气数据"
    args_schema: type[WeatherQuery] = WeatherQuery
    city_adcode_map: dict = {}
    
    def __init__(self):
        """
        初始化天气查询工具
        """
        super().__init__()
        # 城市adcode映射表（部分主要城市）
        self.city_adcode_map = {
            "北京": "110000",
            "上海": "310000",
            "广州": "440100",
            "深圳": "440300",
            "杭州": "330100",
            "成都": "510100",
            "重庆": "500000",
            "武汉": "420100",
            "西安": "610100",
            "南京": "320100",
            "天津": "120000",
            "苏州": "320500",
            "郑州": "410100",
            "长沙": "430100",
            "沈阳": "210100",
            "青岛": "370200",
            "宁波": "330200",
            "东莞": "441900",
            "厦门": "350200"
        }
    
    def _run(self, city_name: str) -> str:
        """
        执行天气查询
        
        Args:
            city_name: 城市名称
            
        Returns:
            格式化的天气信息
        """
        start_time = time.time()
        
        try:
            # 记录工具执行开始
            log_tool_execution(
                tool_name=self.name,
                input_data={"city_name": city_name}
            )
            
            # 获取城市adcode
            adcode = self._get_city_adcode(city_name)
            if not adcode:
                error_msg = f"未找到城市 {city_name} 的adcode"
                app_logger.error(f"天气API返回错误: {error_msg}")
                log_tool_execution(
                    tool_name=self.name,
                    input_data={"city_name": city_name},
                    error=error_msg
                )
                return f"错误：{error_msg}"
            
            # 调用高德地图天气API
            weather_data = self._call_weather_api(adcode)
            
            # 格式化天气信息
            formatted_weather = self._format_weather_info(weather_data, city_name)
            
            # 记录工具执行成功
            execution_time = (time.time() - start_time) * 1000
            log_tool_execution(
                tool_name=self.name,
                input_data={"city_name": city_name},
                output_data={"weather": formatted_weather},
                execution_time=execution_time
            )
            
            return formatted_weather
            
        except Exception as e:
            error_msg = str(e)
            app_logger.error(f"天气API返回错误: {error_msg}")
            
            # 记录工具执行失败
            execution_time = (time.time() - start_time) * 1000
            log_tool_execution(
                tool_name=self.name,
                input_data={"city_name": city_name},
                error=error_msg,
                execution_time=execution_time
            )
            
            return f"错误：{error_msg}"
    
    def _get_city_adcode(self, city_name: str) -> Optional[str]:
        """
        获取城市的adcode
        
        Args:
            city_name: 城市名称
            
        Returns:
            城市的adcode，未找到返回None
        """
        # 标准化城市名称
        city_name = city_name.strip()
        
        # 直接从映射表中获取
        if city_name in self.city_adcode_map:
            app_logger.info(f"城市 {city_name} 的adcode: {self.city_adcode_map[city_name]}")
            return self.city_adcode_map[city_name]
        
        # 尝试去掉"市"字后查找
        if city_name.endswith("市"):
            short_city_name = city_name[:-1]
            if short_city_name in self.city_adcode_map:
                app_logger.info(f"城市 {city_name} 的adcode: {self.city_adcode_map[short_city_name]}")
                return self.city_adcode_map[short_city_name]
        
        app_logger.warning(f"未找到城市 {city_name} 的adcode")
        return None
    
    def _call_weather_api(self, adcode: str) -> Dict[str, Any]:
        """
        调用高德地图天气API
        
        Args:
            adcode: 城市adcode
            
        Returns:
            天气API返回的数据
        """
        url = f"{settings.api.amap_base_url}/weather/weatherInfo"
        params = {
            "key": settings.api.amap_api_key,
            "city": adcode,
            "extensions": "base",  # base: 基础天气, all: 详细天气
            "output": "json"
        }
        
        try:
            start_time = time.time()
            response = requests.get(url, params=params, timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            # 记录API调用
            log_api_call(
                api_name="amap_weather",
                method="GET",
                url=url,
                status_code=response.status_code,
                response_time=response_time
            )
            
            response.raise_for_status()
            data = response.json()
            
            # 检查API返回状态
            if data.get("status") != "1":
                error_msg = data.get("info", "未知错误")
                app_logger.error(f"天气API返回错误: {error_msg}")
                raise Exception(f"API调用失败: {error_msg}")
            
            return data
            
        except requests.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            app_logger.error(f"天气API返回错误: {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = str(e)
            app_logger.error(f"天气API返回错误: {error_msg}")
            raise
    
    def _format_weather_info(self, weather_data: Dict[str, Any], city_name: str) -> str:
        """
        格式化天气信息
        
        Args:
            weather_data: 天气API返回的数据
            city_name: 城市名称
            
        Returns:
            格式化的天气信息字符串
        """
        try:
            # 提取天气数据
            lives = weather_data.get("lives", [])
            if not lives:
                return f"未获取到 {city_name} 的天气信息"
            
            weather_info = lives[0]
            
            # 构建格式化输出
            formatted = f"📍 城市：{city_name}\n"
            formatted += f"🌤️ 天气：{weather_info.get('weather', '未知')}\n"
            formatted += f"🌡️ 温度：{weather_info.get('temperature', '未知')}°C\n"
            formatted += f"💧 湿度：{weather_info.get('humidity', '未知')}%\n"
            formatted += f"💨 风向：{weather_info.get('winddirection', '未知')}\n"
            formatted += f"🌬️ 风力：{weather_info.get('windpower', '未知')}\n"
            formatted += f"🌅 日出：{weather_info.get('sunrise', '未知')}\n"
            formatted += f"🌄 日落：{weather_info.get('sunset', '未知')}\n"
            formatted += f"📅 更新时间：{weather_info.get('reporttime', '未知')}\n"
            
            return formatted
            
        except Exception as e:
            error_msg = f"格式化天气信息失败: {str(e)}"
            app_logger.error(f"天气API返回错误: {error_msg}")
            return f"错误：{error_msg}"


# 创建全局实例
weather_tool = AmapWeatherTool()
