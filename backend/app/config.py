"""
FastAPI 应用配置
从统一的 config/settings.py 导入配置
"""
import os
import sys

# 添加项目根目录到路径
# backend/app/config.py -> backend/app/ -> backend/ -> 项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 重新导出统一的配置
from config.settings import settings

__all__ = ['settings']
