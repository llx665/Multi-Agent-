"""
销售Agent Skill
处理产品推荐、价格咨询等销售相关场景

数据来源：
- 产品折扣数据从 data/skills_data/product_discounts.yaml 加载

智能推荐逻辑：
1. 提取用户想要的推荐数量（默认5个）
2. 识别产品类型（手机、电脑、耳机等）
3. 识别价位需求
4. 综合匹配后限制返回数量
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from loguru import logger

from ..base import BaseSkill, SkillConfig, SkillResult, SkillType
from ..data_loader import skills_data_loader


# 产品类型关键词映射
CATEGORY_KEYWORDS = {
    "手机": ["手机", "phone"],
    "电脑": ["电脑", "笔记本", "laptop", "pc"],
    "平板": ["平板", "pad", "ipad", "matepad"],
    "耳机": ["耳机", "headphone", "earphone", "airpod", "蓝牙耳机"],
    "手表": ["手表", "watch", "手环", "智能手表"],
    "鼠标键盘": ["鼠标", "mouse", "键盘", "keyboard"],
    "路由器": ["路由器", "router", "无线路由"],
    "显示器": ["显示器", "monitor", "屏幕", "屏幕"],
    "游戏设备": ["游戏", "gaming", "电竞", "rog", "拯救者"],
    "音箱": ["音箱", "speaker", "音响"],
    "投影仪": ["投影", "投影仪", "projector"],
    "牙刷": ["牙刷", "电动牙刷", "牙刷"],
}


class SalesAgentSkill(BaseSkill):
    """销售Agent Skill"""

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)
        self._data_loader = skills_data_loader

    def _get_product_cache(self) -> Dict[str, Dict]:
        """获取产品数据缓存（懒加载）"""
        return self._data_loader.get_product_discounts()

    def _get_default_config(self) -> SkillConfig:
        return SkillConfig(
            name="sales_agent",
            description="处理产品咨询、价格查询、购买推荐等销售场景。当用户询问产品、价格、购买时激活。",
            skill_type=SkillType.SALES,
            priority=10
        )

    def should_activate(self, context: Dict[str, Any]) -> bool:
        """判断是否应该激活"""
        query = context.get("query", "").lower()

        sales_keywords = [
            "买", "价格", "多少钱", "推荐", "产品",
            "优惠", "折扣", "促销", "购买", "订购", "手机", "电脑",
            "平板", "耳机", "手表", "鼠标", "键盘", "投影仪", "音箱",
            "牙刷", "电动牙刷"
        ]

        return any(keyword in query for keyword in sales_keywords)

    def _extract_product_names(self, query: str, rag_results: List[Dict] = None, category: Optional[str] = None, history: List[Dict] = None) -> List[str]:
        """
        从用户 query 和 RAG 检索结果中提取产品名称

        Args:
            query: 用户查询文本
            rag_results: RAG 检索结果列表
            category: 已提取的产品类型（如果有）
            history: 对话历史（用于解析"第二款"等指代）

        Returns:
            匹配的产品关键词列表
        """
        query_lower = query.lower()
        matched_products = []

        number_map = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
            "6": 6, "7": 7, "8": 8, "9": 9, "10": 10
        }

        import re

        # 优先：从历史中解析之前推荐的产品列表
        if history and any(kw in query_lower for kw in ["第二款", "第一款", "第三款", "第四款", "第五款", "哪款", "这款", "那个"]):
            history_products = self._parse_products_from_history(history)
            if history_products:
                logger.info(f"[SalesSkill] 从历史中解析到 {len(history_products)} 个产品: {[p['name'] for p in history_products]}")

                # 根据"第X款"匹配具体产品
                for m in re.findall(r'第([一二三四五六七八九十\d]+)[个款号]', query_lower):
                    if m in number_map:
                        idx = number_map[m] - 1
                        if 0 <= idx < len(history_products):
                            product = history_products[idx]
                            # 尝试匹配产品缓存中的产品
                            for key, cache in self._get_product_cache().items():
                                if cache.get("name") == product["name"] or cache.get("name") in product["name"]:
                                    matched_products.append(key)
                                    logger.info(f"[SalesSkill] 历史指代: 第{m}款 = {cache.get('name')}")
                                    break
                            else:
                                # 如果没有精确匹配，返回产品名
                                if not matched_products:
                                    matched_products.append(product["name"])
                                    logger.info(f"[SalesSkill] 历史指代: 第{m}款 = {product['name']} (未在缓存中找到)")

                if matched_products:
                    return matched_products

        index_pattern = r'第([一二三四五六七八九十\d]+)[个款号]'
        matches = re.findall(index_pattern, query_lower)

        if matches:
            all_products = list(self._get_product_cache().keys())
            for m in matches:
                if m in number_map:
                    idx = number_map[m] - 1
                    if 0 <= idx < len(all_products):
                        matched_products.append(all_products[idx])
            if matched_products:
                logger.info(f"[SalesSkill] 检测到序号查询: {matches}, 返回产品: {matched_products}")
                return matched_products

        # 只有在未指定类型时才使用通用查询（返回所有产品）
        # 如果已指定类型，返回空列表让后续按类型过滤
        if category:
            logger.info(f"[SalesSkill] 已有类型={category}，不返回全部产品，等待类型过滤")
            return []

        # 检查是否包含任何类别关键词（即使未在 CATEGORY_KEYWORDS 中匹配到）
        has_any_category_keyword = False
        for cat_keywords in CATEGORY_KEYWORDS.values():
            if any(kw in query_lower for kw in cat_keywords):
                has_any_category_keyword = True
                break

        # 如果查询中有明确的类别关键词（如"牙刷"），不应返回所有产品
        # 只在没有类别意图时才使用通用查询
        general_keywords = ["产品", "商品", "推荐", "看看", "全部", "所有", "都有", "销售", "卖"]
        is_general_query = any(kw in query_lower for kw in general_keywords)

        if is_general_query and len(query) < 15 and not has_any_category_keyword:
            matched_products = list(self._get_product_cache().keys())
            logger.info(f"[SalesSkill] 检测到通用查询，返回所有产品: {matched_products}")
            return matched_products

        # 如果有类别关键词但未匹配到对应类型，返回空列表
        if has_any_category_keyword:
            logger.info(f"[SalesSkill] 查询包含类别关键词但未匹配到已知类型，返回空列表")
            return []

        # 从 RAG 结果中提取产品名
        if rag_results:
            for doc in rag_results:
                content = doc.get("content", "").lower()
                for product_key, product_info in self._get_product_cache().items():
                    if product_key in content and product_key not in matched_products:
                        matched_products.append(product_key)

        # 从 query 中直接匹配产品关键词
        for product_key in self._get_product_cache().keys():
            product_name = self._get_product_cache()[product_key]["name"]
            name_variants = [product_key]
            if " " in product_key:
                name_variants.append(product_key.replace(" ", ""))

            for variant in name_variants:
                if variant in query_lower and variant not in matched_products:
                    matched_products.append(variant)
                    break

        logger.info(f"[SalesSkill] 从 query='{query}' 中提取到产品: {matched_products}")
        return matched_products

    def _parse_products_from_history(self, history: List[Dict]) -> List[Dict]:
        """
        从对话历史中解析之前推荐的产品列表

        Args:
            history: 对话历史列表

        Returns:
            产品列表，每个产品包含 name, price, min_price
        """
        products = []
        import re

        # 遍历历史中的助手回复
        for msg in history:
            if msg.get("role") != "assistant":
                continue

            content = msg.get("content", "")
            if not content:
                continue

            # 匹配 【产品名称】 格式
            product_pattern = r"【([^】]+)】"
            matches = re.findall(product_pattern, content)

            for name in matches:
                # 检查是否已存在
                if not any(p["name"] == name for p in products):
                    # 尝试从产品缓存中获取价格
                    for key, cache in self._get_product_cache().items():
                        if cache.get("name") == name:
                            products.append({
                                "name": name,
                                "price": cache.get("list_price"),
                                "min_price": cache.get("min_price"),
                                "product_key": key
                            })
                            break
                    else:
                        # 如果不在缓存中，只保存名称
                        products.append({"name": name})

            # 如果已经找到产品，就不需要继续了
            if products:
                break

        logger.info(f"[SalesSkill] 从历史中解析出 {len(products)} 个产品")
        return products

    def _extract_recommendation_count(self, query: str) -> Optional[int]:
        """
        从 query 中提取推荐数量

        Args:
            query: 用户查询文本

        Returns:
            推荐数量，如果没有指定则返回 None
        """
        query_lower = query.lower()

        # 阿拉伯数字匹配 - 扩展更多模式
        arabic_patterns = [
            # 给我/给我推荐 + 数字 + 个/款
            r"给我?推荐?(\d+)个?",
            r"给我?(\d+)款?",
            # 推荐/看看 + 数字 + 个/款
            r"推荐?(\d+)个?",
            r"推荐?(\d+)款?",
            r"看看?(\d+)个?",
            r"看看?(\d+)款?",
            # 给我 + 数字 + 个产品
            r"给我?(\d+)个?产品",
            r"有?(\d+)款?产品",
            # 介绍 + 数字 + 个/款
            r"介绍?(\d+)个?",
            r"介绍?(\d+)款?",
            # 还有/再 + 数字 + 个/款
            r"还有?(\d+)个?",
            r"还有?(\d+)款?",
            r"再?(\d+)个?",
            r"再?(\d+)款?",
            # 想要 + 数字 + 个/款
            r"想要?(\d+)个?",
            r"想要?(\d+)款?",
        ]
        for pattern in arabic_patterns:
            match = re.search(pattern, query_lower)
            if match:
                count = int(match.group(1))
                if 1 <= count <= 20:  # 限制范围
                    logger.info(f"[SalesSkill] 阿拉伯数字提取: 模式={pattern}, 数量={count}")
                    return count

        # 中文数字匹配
        chinese_map = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12, "十几": 10, "十多": 10
        }
        chinese_patterns = [
            r"给我?推荐?([一二三四五六七八九十]+)个?",
            r"给我?([一二三四五六七八九十]+)款?",
            r"推荐?([一二三四五六七八九十]+)个?",
            r"推荐?([一二三四五六七八九十]+)款?",
            r"给我?([一二三四五六七八九十]+)个?产品",
            r"介绍?([一二三四五六七八九十]+)个?",
            r"介绍?([一二三四五六七八九十]+)款?",
            r"还有?([一二三四五六七八九十]+)个?",
            r"还有?([一二三四五六七八九十]+)款?",
            r"再?([一二三四五六七八九十]+)个?",
            r"再?([一二三四五六七八九十]+)款?",
        ]
        for pattern in chinese_patterns:
            match = re.search(pattern, query_lower)
            if match:
                chinese_num = match.group(1)
                if chinese_num in chinese_map:
                    count = chinese_map[chinese_num]
                    logger.info(f"[SalesSkill] 中文数字提取: {chinese_num} -> {count}")
                    return count

        # 模糊数量词匹配（"几款"、"几个"、"有哪款"）
        if re.search(r"几[个款]", query_lower) or "有哪款" in query_lower:
            logger.info(f"[SalesSkill] 模糊数量词提取: 3")
            return 3

        # "所有"、"全部"等不限制数量
        if any(kw in query_lower for kw in ["所有", "全部", "都有", "都有哪些"]):
            logger.info(f"[SalesSkill] 全量查询，不限制数量")
            return None

        logger.info(f"[SalesSkill] 未提取到数量，使用默认值")
        return None

    def _extract_product_category(self, query: str) -> Optional[str]:
        """
        从 query 中提取产品类型

        Args:
            query: 用户查询文本

        Returns:
            产品类型（如 "手机"、"耳机"），如果没有指定则返回 None
        """
        query_lower = query.lower()

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                logger.info(f"[SalesSkill] 提取到产品类型: {category}")
                return category

        return None

    def _filter_by_category_and_budget(
        self,
        query: str,
        category: Optional[str] = None,
        budget_info: Optional[Dict] = None
    ) -> List[str]:
        """
        根据类型和预算过滤产品

        Args:
            query: 用户查询
            category: 产品类型
            budget_info: 预算信息

        Returns:
            匹配的产品关键词列表
        """
        all_products = list(self._get_product_cache().keys())
        matched = []

        for key in all_products:
            product = self._get_product_cache()[key]
            product_name = product.get("name", "").lower()
            product_key_lower = key.lower()

            # 1. 类型过滤
            if category:
                category_keywords = CATEGORY_KEYWORDS.get(category, [])
                if not any(kw in product_name or kw in product_key_lower for kw in category_keywords):
                    continue

            # 2. 预算过滤
            if budget_info:
                price = product.get("list_price", 0) or 0
                budget_type = budget_info.get("type")

                if budget_type == "budget_under":
                    # 提取预算金额
                    match = re.search(r"(\d+)", budget_info.get("match", ""))
                    if match:
                        budget = int(match.group(1)) * 1000 if "千" in budget_info.get("match", "") else int(match.group(1))
                        if price > budget:
                            continue

                elif budget_type == "budget_low":
                    if price > 2000:
                        continue

                elif budget_type == "budget_high":
                    if price < 5000:
                        continue

            matched.append(key)

        logger.info(f"[SalesSkill] 类型={category}, 预算={budget_info}, 匹配产品数={len(matched)}")
        return matched

    def _match_budget_product(self, query: str) -> Optional[Dict]:
        """
        根据预算匹配产品

        Args:
            query: 用户查询

        Returns:
            匹配的产品信息或 None
        """
        query_lower = query.lower()

        # 预算关键词匹配
        budget_patterns = {
            r"(\d+)[千千]?以?[内下]": ("budget_under", int),
            r"(\d+)[千千]?左右": ("budget_around", int),
            r"(\d+)[千千]?以?[外上]": ("budget_over", int),
            r"便宜.{0,5}|[Ss]imple|入门": ("budget_low", None),
            r"贵|旗舰|高端|最好": ("budget_high", None),
        }

        for pattern, (budget_type, _) in budget_patterns.items():
            match = re.search(pattern, query_lower)
            if match:
                return {"type": budget_type, "match": match.group(0) if match else None}

        return None

    def _get_recommendations(
        self,
        product_keys: List[str],
        user_preference: str = None,
        max_count: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取产品推荐列表

        Args:
            product_keys: 产品关键词列表
            user_preference: 用户偏好描述
            max_count: 最大推荐数量

        Returns:
            产品推荐列表（限制数量）
        """
        recommendations = []

        for key in product_keys:
            if key in self._get_product_cache():
                product = self._get_product_cache()[key].copy()
                product["product_key"] = key
                recommendations.append(product)

        # 如果没有精确匹配，根据用户偏好推荐
        if not recommendations and user_preference:
            recommendations = self._get_preference_based_recommendations(user_preference)

        # 按价格排序（从低到高）
        recommendations.sort(key=lambda x: x.get("list_price", 0) or 0)

        # 限制返回数量
        limited = recommendations[:max_count]
        logger.info(f"[SalesSkill] 推荐数量: 请求max={max_count}, 实际返回={len(limited)}")
        return limited

    def _get_preference_based_recommendations(self, preference: str) -> List[Dict]:
        """根据用户偏好获取推荐"""
        preference_lower = preference.lower()
        matched = []

        # 按偏好类型匹配
        for key, product in self._get_product_cache().items():
            if any(kw in preference_lower for kw in ["游戏", "电竞", "gaming"]):
                if "拯救者" in product["name"] or "游戏" in product["name"]:
                    matched.append(product.copy())
            elif any(kw in preference_lower for kw in ["办公", "商务", "工作"]):
                if "ThinkBook" in product["name"] or "MatePad" in product["name"]:
                    matched.append(product.copy())
            elif any(kw in preference_lower for kw in ["听歌", "音乐", "音质"]):
                if "耳机" in product["name"] or "音箱" in product["name"]:
                    matched.append(product.copy())

        return matched[:3]

    def _generate_sales_response(
        self,
        products: List[Dict[str, Any]],
        customer_type: str = None
    ) -> str:
        """
        生成销售推荐话术（口语化版本）

        Args:
            products: 产品列表
            customer_type: 客户类型

        Returns:
            口语化推荐话术
        """
        if not products:
            return "哎呀，目前没有找到特别符合您需求的产品呢～要不您说说看大概想要什么价位的，或者有什么特别的要求吗？我再帮您挑挑看！"

        intro_templates = [
            "好的，我给您推荐几款不错的：",
            "根据您的情况，我整理了几款性价比很高的产品：",
            "来来来，我给您看看这几款，保准有您喜欢的！",
            "帮您搜罗了一下，目前比较热门的有这几款："
        ]
        import random
        intro = random.choice(intro_templates)

        response_parts = [intro]
        for i, product in enumerate(products, 1):
            name = product['name']
            list_price = product['list_price']
            min_price = product['min_price']

            discount = list_price - min_price
            discount_percent = int(discount / list_price * 100) if list_price > 0 else 0

            response_parts.append(
                f"【{name}】\n"
                f"   标价 {list_price} 元，现在搞活动最低可以到 {min_price} 元，"
                f"能省 {discount} 块呢（约等于打了 {100-discount_percent} 折）！"
            )

        outro_templates = [
            "\n\n怎么样，有没有看中的？",
            "\n\n您对哪款比较感兴趣？我可以给您详细说说～",
            "\n\n这几款都是现在卖得不错的，您可以参考一下！"
        ]
        outro = random.choice(outro_templates)

        return "\n".join(response_parts) + outro

    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行销售处理

        从知识库查询产品信息，生成个性化推荐
        """
        try:
            query = context.get("query", "")
            rag_results = context.get("rag_results", [])
            customer_type = context.get("customer_type", None)
            user_preference = context.get("preference", None)
            # 获取历史记录用于解析"第二款"等指代
            history = context.get("history", [])

            # 1. 提取推荐数量（默认5个）
            recommend_count = self._extract_recommendation_count(query)
            if recommend_count is None:
                recommend_count = 5

            # 2. 提取产品类型
            category = self._extract_product_category(query)

            # 3. 提取预算信息
            budget_info = self._match_budget_product(query)

            # 4. 优先从 RAG 结果和 query 中提取具体产品名
            # 传入 category 和 history 以支持上下文指代
            matched_products = self._extract_product_names(query, rag_results, category, history)

            # 5. 如果没有指定具体产品，根据类型和预算匹配
            if not matched_products:
                matched_products = self._filter_by_category_and_budget(
                    query, category, budget_info
                )

            # 6. 获取推荐（限制数量）
            recommendations = self._get_recommendations(
                matched_products,
                user_preference,
                max_count=recommend_count
            )
            logger.info(f"[SalesSkill] 匹配产品: {matched_products}, 推荐: {[p.get('name') for p in recommendations]}")

            # 7. 计算评估分数
            evaluation_score = self._calculate_evaluation_score(
                query=query,
                matched_products=matched_products,
                recommendations=recommendations,
                rag_results=rag_results
            )

            response_data = {
                "intent": "sales",
                "products_mentioned": matched_products,
                "products_recommended": [
                    {"name": p["name"], "price": p["list_price"], "min_price": p["min_price"]}
                    for p in recommendations
                ],
                "action": "product_recommendation",
                "recommend_count": recommend_count,
                "category": category,
                "follow_up_needed": len(recommendations) > 0,
                "recommendation_response": self._generate_sales_response(recommendations, customer_type)
            }

            logger.info(f"[SalesSkill] 推荐了 {len(recommendations)} 个产品 (请求: {recommend_count}, 类型: {category})")

            return SkillResult(
                success=True,
                data=response_data,
                message="产品推荐已生成",
                confidence=0.9 if recommendations else 0.5,
                evaluation_score=evaluation_score
            )

        except Exception as e:
            logger.error(f"销售Skill执行失败: {str(e)}")
            return SkillResult(
                success=False,
                error=str(e),
                evaluation_score=0.0
            )

    def _get_budget_matched_products(
        self,
        budget_info: Dict,
        query: str
    ) -> List[str]:
        """根据预算信息匹配产品"""
        budget_type = budget_info.get("type")
        products = []

        for key, product in self._get_product_cache().items():
            price = product.get("list_price") or product.get("price", 0)

            if budget_type == "budget_under":
                # 提取预算金额
                match = re.search(r"(\d+)", budget_info.get("match", ""))
                if match:
                    budget = int(match.group(1)) * 1000 if "千" in budget_info.get("match", "") else int(match.group(1))
                    if price <= budget:
                        products.append(key)

        return products

    def _calculate_evaluation_score(
        self,
        query: str,
        matched_products: List[str],
        recommendations: List[Dict],
        rag_results: List[Dict]
    ) -> float:
        """
        计算 Skill 输出质量评分

        评分维度：
        - 产品匹配度：是否准确识别用户需求
        - RAG 利用度：是否有效利用检索结果
        - 推荐合理性：价格和需求是否匹配
        """
        score = 0.5  # 基础分

        # 产品匹配
        if matched_products:
            score += 0.2

        # 有推荐结果
        if recommendations:
            score += 0.15

        # RAG 结果有效利用
        if rag_results and any(r.get("similarity_score", 0) > 0.5 for r in rag_results):
            score += 0.1

        # 推荐数量合理（1-3个）
        if 1 <= len(recommendations) <= 3:
            score += 0.05

        return min(score, 1.0)

    def get_prompt(self) -> str:
        """获取销售专用提示词"""
        return """你是一个专业的销售顾问。要点：
1. 主动了解客户需求（预算、使用场景、偏好）
2. 根据需求推荐最合适的产品
3. 熟悉产品特点和价格，能专业解答疑问
4. 适时推荐性价比高的产品
5. 处理价格咨询，在权限范围内给予优惠
6. 促进交易达成，但不强买强卖"""
