"""
BM25 专业排序算法模块
=====================

完整的 BM25 (Best Matching 25) 算法实现，专门优化用于中文电商场景。

核心特性：
1. 完整的 TF-IDF 计算 - 使用经典 BM25 公式
2. 文档长度归一化 - 自适应平均文档长度
3. 可调参数 - k1 (词频饱和) 和 b (文档长度归一化)
4. 中文分词支持 - jieba 分词集成
5. 电商停用词 - 产品无关高频词过滤
6. 查询扩展 - 同义词和产品型号扩展
7. 批量索引 - 高效批量文档索引

BM25 公式：
    score(D, Q) = Σ IDF(qi) * (tf(ti,D) * (k1+1)) / (tf(ti,D) + k1 * (1 - b + b * |D|/avgdl))

Author: test2langchain
"""

import math
import re
import hashlib
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import Counter
import threading


class BM25Stopwords:
    """BM25 停用词管理器"""

    DEFAULT_STOPWORDS: Set[str] = {
        # 真正的通用停用词 - 这些词出现在几乎所有文档中，无任何区分度
        # 注意：只保留真正泛化的词，不要过滤产品核心关键词

        # 极高频通用词
        "的", "了", "和", "是", "在", "有", "我", "这", "那", "个",
        "不", "也", "都", "就", "要", "会", "能", "可", "为", "与",
        # 文档结构词
        "产品介绍", "产品名称", "产品特点", "产品优势", "产品信息",
        "序号", "编号", "成本价", "标价",
        # 极泛化描述词（这些词几乎每个产品都有）
        "官网", "客服", "电话", "邮箱", "网址", "地址",
        "正品", "保障", "退货", "售后", "保修", "服务",
        "全新", "官方", "旗舰", "顶级",
        # 常见连接词
        "以及", "还有", "并且", "而且", "但是", "然而",
        "因为", "所以", "如果", "虽然",
    }

    def __init__(self, custom_stopwords: Optional[Set[str]] = None):
        self.stopwords = self.DEFAULT_STOPWORDS.copy()
        if custom_stopwords:
            self.stopwords.update(custom_stopwords)

    def is_stopword(self, word: str) -> bool:
        """检查是否为停用词"""
        return word.lower() in self.stopwords

    def filter(self, tokens: List[str]) -> List[str]:
        """过滤停用词"""
        return [t for t in tokens if t.lower() not in self.stopwords and len(t) >= 2]


@dataclass
class BM25Document:
    """BM25 索引文档"""
    id: str
    content: str
    tokens: List[str] = field(default_factory=list)
    token_freq: Dict[str, int] = field(default_factory=dict)
    length: int = 0


@dataclass
class BM25Result:
    """BM25 检索结果"""
    doc_id: str
    score: float
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ECommerceTokenizer:
    """电商领域专用分词器"""

    PRODUCT_MODEL_PATTERN = re.compile(
        r'[a-zA-Z](?:\d{1,4}|\d+[a-zA-Z]?(?:\s*(?:pro|max|plus|air|mini|se|ultra|note|turbo|青春版|尊享版|套装版))?)|'
        r'(?:(?:X|Y|Z)\d+(?:[A-Z])?(?:\s*(?:Pro|Max|Plus|Air|Mini|SE))?)'
    )

    NUMBER_UNIT_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(英寸寸|寸|小时|h|分|分钟|秒|s|米|m|克|g|千克|kg|瓦|w|度|度电|毫安|mah)+')

    def __init__(self, use_jieba: bool = True):
        self.use_jieba = use_jieba
        self.jieba = None
        self._init_jieba()

    def _init_jieba(self):
        """初始化 jieba 分词"""
        if self.use_jieba:
            try:
                import jieba
                self.jieba = jieba
                jieba.initialize()
            except ImportError:
                self.use_jieba = False

    def tokenize(self, text: str) -> List[str]:
        """
        分词

        Args:
            text: 输入文本

        Returns:
            分词列表
        """
        if not text:
            return []

        text = text.lower().strip()
        tokens = []

        if self.jieba:
            jieba_tokens = list(self.jieba.cut(text, cut_all=False))
            tokens.extend([t.strip() for t in jieba_tokens if t.strip() and len(t.strip()) >= 2])
        else:
            tokens.extend(self._simple_tokenize(text))

        tokens.extend(self._extract_product_models(text))
        tokens.extend(self._extract_number_units(text))

        return tokens

    def _simple_tokenize(self, text: str) -> List[str]:
        """简单分词（无 jieba 时使用）"""
        tokens = []
        text = re.sub(r'[^\w\s]', ' ', text)

        chinese_segments = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_segments:
            for i in range(len(segment)):
                for length in [2, 3, 4]:
                    if i + length <= len(segment):
                        tokens.append(segment[i:i+length])

        english_tokens = re.findall(r'[a-zA-Z0-9]+', text)
        tokens.extend([t.lower() for t in english_tokens if len(t) >= 2])

        return tokens

    def _extract_product_models(self, text: str) -> List[str]:
        """提取产品型号"""
        models = []
        matches = self.PRODUCT_MODEL_PATTERN.findall(text.lower())
        for match in matches:
            clean_match = match.strip()
            if len(clean_match) >= 2:
                models.append(clean_match)
                if ' ' in clean_match:
                    models.append(clean_match.replace(' ', ''))
        return models

    def _extract_number_units(self, text: str) -> List[str]:
        """提取数字+单位组合"""
        units = []
        matches = self.NUMBER_UNIT_PATTERN.findall(text.lower())
        for num, unit in matches:
            units.append(f"{num}{unit}")
        return units


class BM25ParameterTuner:
    """BM25 参数调优器"""

    DEFAULT_K1_RANGE = [0.5, 1.0, 1.2, 1.5, 1.8, 2.0]
    DEFAULT_B_RANGE = [0.3, 0.5, 0.6, 0.75, 0.8, 0.9]

    def __init__(self, k1_range: Optional[List[float]] = None, b_range: Optional[List[float]] = None):
        self.k1_range = k1_range or self.DEFAULT_K1_RANGE
        self.b_range = b_range or self.DEFAULT_B_RANGE

    def grid_search(
        self,
        bm25: 'ProfessionalBM25',
        test_queries: List[Tuple[str, List[str]]],
        top_k: int = 10
    ) -> Dict[str, float]:
        """
        网格搜索最优参数

        Args:
            bm25: BM25 实例
            test_queries: 测试查询列表，每项为 (query, relevant_doc_ids)
            top_k: 评估时返回的前k个结果

        Returns:
            最优参数 {'k1': xx, 'b': xx, 'map': xx}
        """
        best_params = {'k1': 1.5, 'b': 0.75, 'map': 0.0}

        for k1 in self.k1_range:
            for b in self.b_range:
                bm25.k1 = k1
                bm25.b = b

                map_score = self._calculate_map(bm25, test_queries, top_k)
                if map_score > best_params['map']:
                    best_params = {'k1': k1, 'b': b, 'map': map_score}

        bm25.k1 = best_params['k1']
        bm25.b = best_params['b']

        return best_params

    def _calculate_map(
        self,
        bm25: 'ProfessionalBM25',
        test_queries: List[Tuple[str, List[str]]],
        top_k: int
    ) -> float:
        """计算平均准确率 (MAP)"""
        average_precisions = []

        for query, relevant_docs in test_queries:
            results = bm25.search(query, top_k)
            result_ids = [r.doc_id for r in results]

            precisions = []
            relevant_count = 0

            for i, doc_id in enumerate(result_ids):
                if doc_id in relevant_docs:
                    relevant_count += 1
                    precisions.append(relevant_count / (i + 1))

            if precisions:
                average_precisions.append(sum(precisions) / len(precisions))

        return sum(average_precisions) / len(average_precisions) if average_precisions else 0.0


class ProfessionalBM25:
    """
    专业 BM25 排序算法实现

    特性：
    - 完整的 BM25 公式实现
    - 线程安全索引操作
    - 电商领域优化
    - 批量文档索引
    - 参数自动调优

    Example:
        bm25 = ProfessionalBM25()
        bm25.index_documents([
            {"id": "1", "content": "蓝牙耳机推荐", "metadata": {"type": "product"}},
            {"id": "2", "content": "无线耳机价格", "metadata": {"type": "product"}}
        ])
        results = bm25.search("蓝牙耳机", top_k=5)
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        use_jieba: bool = True,
        stopwords: Optional[BM25Stopwords] = None,
        epsilon: float = 0.25
    ):
        """
        初始化 BM25

        Args:
            k1: 词频饱和参数，通常在 1.2-2.0 之间
                - 值越大，词频对得分的影响越大
                - 值越小，高频词与低频词的差异越小
            b: 文档长度归一化参数，通常为 0.75
                - 值越大，文档长度对得分的影响越大
                - b=0 时，不考虑文档长度
            use_jieba: 是否使用 jieba 中文分词
            stopwords: 停用词管理器
            epsilon: IDF 平滑参数，防止罕见词 IDF 过高
        """
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon

        self._lock = threading.RLock()

        self.tokenizer = ECommerceTokenizer(use_jieba=use_jieba)
        self.stopwords = stopwords or BM25Stopwords()

        self._documents: Dict[str, BM25Document] = {}
        self._doc_ids: List[str] = []
        self._avg_doc_length: float = 0.0
        self._doc_freq: Counter = Counter()
        self._total_docs: int = 0
        self._total_terms: int = 0

        self._indexed: bool = False

    @property
    def is_indexed(self) -> bool:
        """检查是否已建立索引"""
        return self._indexed

    @property
    def document_count(self) -> int:
        """文档数量"""
        return self._total_docs

    @property
    def vocabulary_size(self) -> int:
        """词汇表大小"""
        return len(self._doc_freq)

    def index_documents(self, documents: List[Dict[str, Any]], batch_size: int = 100):
        """
        批量索引文档

        Args:
            documents: 文档列表，每项包含:
                - id: 文档唯一标识
                - content: 文档内容
                - metadata: 可选的元数据
            batch_size: 批量处理大小
        """
        with self._lock:
            self._documents.clear()
            self._doc_ids.clear()
            self._doc_freq.clear()
            self._total_terms = 0

            for doc in documents:
                doc_id = doc.get('id', str(hashlib.md5(doc['content'].encode()).hexdigest()))
                content = doc.get('content', '')
                metadata = doc.get('metadata', {})

                tokens = self.tokenizer.tokenize(content)
                tokens = self.stopwords.filter(tokens)

                token_freq = Counter(tokens)
                doc_length = len(tokens)

                bm25_doc = BM25Document(
                    id=doc_id,
                    content=content,
                    tokens=tokens,
                    token_freq=token_freq,
                    length=doc_length
                )

                self._documents[doc_id] = bm25_doc
                self._doc_ids.append(doc_id)

                for term, freq in token_freq.items():
                    self._doc_freq[term] += 1
                    self._total_terms += freq

            self._total_docs = len(self._documents)
            self._avg_doc_length = self._total_terms / self._total_docs if self._total_docs > 0 else 0

            self._indexed = True

    def add_document(self, document: Dict[str, Any]):
        """
        添加单个文档到索引

        Args:
            document: 文档，包含 id, content, metadata
        """
        with self._lock:
            doc_id = document.get('id', str(hashlib.md5(document['content'].encode()).hexdigest()))
            content = document.get('content', '')
            metadata = document.get('metadata', {})

            if doc_id in self._documents:
                return

            tokens = self.tokenizer.tokenize(content)
            tokens = self.stopwords.filter(tokens)

            token_freq = Counter(tokens)
            doc_length = len(tokens)

            bm25_doc = BM25Document(
                id=doc_id,
                content=content,
                tokens=tokens,
                token_freq=token_freq,
                length=doc_length
            )

            self._documents[doc_id] = bm25_doc
            self._doc_ids.append(doc_id)

            for term, freq in token_freq.items():
                self._doc_freq[term] += 1
                self._total_terms += freq

            self._total_docs = len(self._documents)
            self._avg_doc_length = self._total_terms / self._total_docs if self._total_docs > 0 else 0

    def remove_document(self, doc_id: str) -> bool:
        """
        从索引中移除文档

        Args:
            doc_id: 文档ID

        Returns:
            是否成功移除
        """
        with self._lock:
            if doc_id not in self._documents:
                return False

            doc = self._documents[doc_id]
            for term in doc.token_freq:
                self._doc_freq[term] -= 1
                if self._doc_freq[term] <= 0:
                    del self._doc_freq[term]
                self._total_terms -= doc.token_freq[term]

            del self._documents[doc_id]
            self._doc_ids.remove(doc_id)
            self._total_docs = len(self._documents)
            self._avg_doc_length = self._total_terms / self._total_docs if self._total_docs > 0 else 0

            return True

    def clear(self):
        """清空索引"""
        with self._lock:
            self._documents.clear()
            self._doc_ids.clear()
            self._doc_freq.clear()
            self._total_docs = 0
            self._total_terms = 0
            self._avg_doc_length = 0.0
            self._indexed = False

    def _calculate_idf(self, term: str) -> float:
        """
        计算 IDF（逆文档频率）

        使用 Lucene 风格的平滑公式：
        IDF = log((N - n + 0.5) / (n + 0.5) + 1)

        Args:
            term: 词项

        Returns:
            IDF 值
        """
        n = self._doc_freq.get(term, 0)

        if n == 0:
            return 0.0

        idf = math.log(
            (self._total_docs - n + 0.5) / (n + 0.5) + 1
        )

        return max(idf, self.epsilon)

    def _compute_score(self, doc: BM25Document, term_scores: Dict[str, float]) -> float:
        """
        计算单个文档的 BM25 得分

        Args:
            doc: 索引文档
            term_scores: 每个查询词对文档的得分

        Returns:
            BM25 得分
        """
        score = 0.0

        for term, component_score in term_scores.items():
            if term in doc.token_freq:
                tf = doc.token_freq[term]
                idf = self._calculate_idf(term)

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc.length / max(self._avg_doc_length, 1))

                score += idf * (numerator / denominator)

        return score

    def search(
        self,
        query: str,
        top_k: int = 10,
        include_metadata: bool = True
    ) -> List[BM25Result]:
        """
        BM25 检索

        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            include_metadata: 是否包含文档元数据

        Returns:
            排序后的结果列表
        """
        with self._lock:
            if not self._indexed or self._total_docs == 0:
                return []

            query_tokens = self.tokenizer.tokenize(query)
            query_tokens = self.stopwords.filter(query_tokens)

            if not query_tokens:
                return []

            query_token_set = set(query_tokens)

            term_doc_scores: Dict[str, Dict[str, float]] = {}
            for term in query_token_set:
                term_doc_scores[term] = {}

                for doc_id in self._doc_ids:
                    doc = self._documents[doc_id]
                    if term in doc.token_freq:
                        tf = doc.token_freq[term]
                        idf = self._calculate_idf(term)

                        numerator = tf * (self.k1 + 1)
                        denominator = tf + self.k1 * (1 - self.b + self.b * doc.length / max(self._avg_doc_length, 1))

                        term_doc_scores[term][doc_id] = idf * (numerator / denominator)

            doc_scores: Dict[str, float] = {}
            for doc_id in self._doc_ids:
                score = 0.0
                for term in query_token_set:
                    if doc_id in term_doc_scores[term]:
                        score += term_doc_scores[term][doc_id]
                if score > 0:
                    doc_scores[doc_id] = score

            sorted_doc_ids = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

            results = []
            for doc_id, score in sorted_doc_ids[:top_k]:
                doc = self._documents[doc_id]
                metadata = doc.content[:200] if not include_metadata else {}

                results.append(BM25Result(
                    doc_id=doc_id,
                    score=score,
                    content=doc.content,
                    metadata=metadata
                ))

            return results

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        with self._lock:
            return {
                "document_count": self._total_docs,
                "vocabulary_size": len(self._doc_freq),
                "avg_doc_length": round(self._avg_doc_length, 2),
                "total_terms": self._total_terms,
                "parameters": {
                    "k1": self.k1,
                    "b": self.b,
                    "epsilon": self.epsilon
                },
                "top_terms": [
                    {"term": term, "doc_freq": freq}
                    for term, freq in self._doc_freq.most_common(20)
                ]
            }

    def tune_parameters(
        self,
        test_queries: List[Tuple[str, List[str]]],
        top_k: int = 10
    ) -> Dict[str, float]:
        """
        自动调优 BM25 参数

        Args:
            test_queries: 测试查询列表，每项为 (query, relevant_doc_ids)
            top_k: 评估时返回的前k个结果

        Returns:
            最优参数 {'k1': xx, 'b': xx, 'map': xx}
        """
        tuner = BM25ParameterTuner()
        return tuner.grid_search(self, test_queries, top_k)


def create_bm25_ranker(
    k1: float = 1.5,
    b: float = 0.75,
    use_jieba: bool = True,
    custom_stopwords: Optional[Set[str]] = None
) -> ProfessionalBM25:
    """
    创建 BM25 排序器工厂函数

    Args:
        k1: 词频饱和参数
        b: 文档长度归一化参数
        use_jieba: 是否使用 jieba 分词
        custom_stopwords: 自定义停用词

    Returns:
        ProfessionalBM25 实例
    """
    stopwords = BM25Stopwords(custom_stopwords) if custom_stopwords else None
    return ProfessionalBM25(
        k1=k1,
        b=b,
        use_jieba=use_jieba,
        stopwords=stopwords
    )
