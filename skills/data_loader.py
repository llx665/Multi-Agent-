"""
Skill 数据加载器
从 YAML/JSON 文件加载 Skill 所需的业务数据
"""

import os
import yaml
from typing import Any, Dict, Optional
from functools import lru_cache

from core.logger import LoggerManager

logger = LoggerManager.get_logger("skills_data_loader")


class SkillsDataLoader:
    """
    Skill 业务数据加载器

    功能：
    1. 从 YAML 文件加载产品折扣数据
    2. 从 YAML 文件加载技术支持知识库
    3. 缓存加载结果避免重复读取文件
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

        # 数据目录
        self._data_dir = self._get_data_dir()

        # 缓存
        self._product_discounts: Optional[Dict] = None
        self._tech_support_kb: Optional[Dict] = None

        logger.info(f"[SkillsDataLoader] 初始化完成，数据目录: {self._data_dir}")

    def _get_data_dir(self) -> str:
        """获取数据目录路径"""
        # 向上找到项目根目录
        current = os.path.dirname(os.path.dirname(__file__))
        data_dir = os.path.join(current, "data", "skills_data")

        if not os.path.exists(data_dir):
            logger.warning(f"[SkillsDataLoader] 数据目录不存在: {data_dir}")
            # 尝试项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current)))
            data_dir = os.path.join(project_root, "data", "skills_data")

        return data_dir

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载 YAML 文件"""
        file_path = os.path.join(self._data_dir, filename)

        if not os.path.exists(file_path):
            logger.error(f"[SkillsDataLoader] 文件不存在: {file_path}")
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            logger.info(f"[SkillsDataLoader] 加载成功: {filename}")
            return data or {}
        except Exception as e:
            logger.error(f"[SkillsDataLoader] 加载失败 {filename}: {e}")
            return {}

    def get_product_discounts(self) -> Dict[str, Dict]:
        """获取产品折扣数据"""
        if self._product_discounts is None:
            data = self._load_yaml("product_discounts.yaml")
            self._product_discounts = data.get("products", {})
            logger.info(f"[SkillsDataLoader] 产品折扣数据加载完成，共 {len(self._product_discounts)} 个产品")

        return self._product_discounts

    def get_tech_support_kb(self) -> Dict[str, Dict]:
        """获取技术支持知识库"""
        if self._tech_support_kb is None:
            data = self._load_yaml("tech_support_kb.yaml")
            self._tech_support_kb = data.get("issue_types", {})
            logger.info(f"[SkillsDataLoader] 技术支持知识库加载完成，共 {len(self._tech_support_kb)} 种问题类型")

        return self._tech_support_kb

    def reload(self) -> None:
        """重新加载所有数据（用于数据更新）"""
        self._product_discounts = None
        self._tech_support_kb = None
        logger.info("[SkillsDataLoader] 数据缓存已清除，下次访问时将重新加载")


# 全局单例
skills_data_loader = SkillsDataLoader()
