"""
向量数据库管理器
负责ChromaDB的连接、集合管理、文档操作和向量检索
"""

import os
from typing import List, Dict, Any, Optional
from loguru import logger
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.documents import Document
from config.settings import settings
from tools.rag.chroma_telemetry import disable_chroma_telemetry


class LocalEmbeddings:
    """本地向量嵌入模型"""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.rag.embedding_model_name
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"嵌入模型初始化完成: {self.model_name}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        """嵌入查询文本"""
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


class VectorDBManager:
    """向量数据库管理器"""

    def __init__(self, embeddings: Optional[LocalEmbeddings] = None):
        """初始化向量数据库管理器

        Args:
            embeddings: 可选的自定义嵌入模型
        """
        self.embeddings = embeddings or LocalEmbeddings()
        self.chroma_client = None
        self.collection = None
        self._db_available = False
        self._collection_name = settings.vector_db.vector_db_collection_name
        self._doc_counter = 0
        self.logger = logger.bind(name="vector_db_manager")

        self._initialize_chromadb()

    def _initialize_chromadb(self) -> None:
        """初始化ChromaDB连接"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            chroma_data_path = os.path.join(project_root, 'chroma_data')
            os.makedirs(chroma_data_path, exist_ok=True)

            disable_chroma_telemetry()
            self.chroma_client = chromadb.PersistentClient(
                path=chroma_data_path,
                settings=ChromaSettings(anonymized_telemetry=False)
            )

            # 尝试获取现有集合，如果存在就保留
            try:
                self.collection = self.chroma_client.get_collection(self._collection_name)
                count = self.collection.count()
                self._db_available = True
                self.logger.info(f"ChromaDB 加载已有集合: {self._collection_name}, 文档数: {count}")
            except Exception:
                # 集合不存在，创建新集合
                try:
                    self.collection = self.chroma_client.create_collection(
                        name=self._collection_name,
                        metadata={"hnsw:space": "l2"}
                    )
                    self._db_available = True
                    self.logger.info(f"ChromaDB 创建新集合: {self._collection_name}")
                except Exception as e:
                    self.logger.error(f"创建集合失败: {e}")
                    self._db_available = False
                    self.collection = None

        except Exception as e:
            self.logger.warning(f"ChromaDB 初始化失败: {e}，向量数据库功能将不可用")
            self.chroma_client = None
            self.collection = None
            self._db_available = False

    def _ensure_collection_exists(self) -> None:
        """确保集合存在，如果不存在则创建

        Raises:
            RuntimeError: 向量数据库不可用或创建集合失败
        """
        if not self._db_available or self.chroma_client is None:
            raise RuntimeError("向量数据库客户端不可用")

        try:
            # 尝试获取集合
            self.collection = self.chroma_client.get_collection(self._collection_name)
            self.logger.debug(f"集合 {self._collection_name} 已存在")
        except Exception:
            # 集合不存在，创建新集合
            try:
                self.collection = self.chroma_client.create_collection(
                    name=self._collection_name,
                    metadata={"hnsw:space": "l2"}
                )
                self.logger.info(f"集合 {self._collection_name} 创建成功")
            except Exception as e:
                self.logger.error(f"创建集合失败: {e}")
                raise RuntimeError(f"无法创建集合: {e}")

    def is_available(self) -> bool:
        """检查向量数据库是否可用

        Returns:
            数据库是否可用
        """
        return self._db_available

    def add_documents(self, documents: List[Document]) -> List[str]:
        """将文档写入向量数据库

        Args:
            documents: 文档列表

        Returns:
            文档ID列表

        Raises:
            RuntimeError: 向量数据库不可用
        """
        # 确保集合存在
        self._ensure_collection_exists()

        if not self._db_available or self.collection is None:
            raise RuntimeError("向量数据库不可用，无法添加文档")

        texts = [doc.page_content for doc in documents]
        embeddings = self.embeddings.embed_documents(texts)

        ids = []
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            doc_id = f"doc_{self._doc_counter}_{i}"
            ids.append(doc_id)

            # 为每个文档块添加chunk_id到元数据
            metadata = doc.metadata.copy() if doc.metadata else {}
            metadata["chunk_id"] = doc_id

            self.collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[doc.page_content],
                metadatas=[metadata]
            )

        self._doc_counter += len(documents)
        self.logger.info(f"{len(documents)}个文档块写入向量数据库")
        return ids

    def delete_document(self, document_id: str) -> bool:
        """删除指定文档

        Args:
            document_id: 文档ID

        Returns:
            是否删除成功

        Raises:
            RuntimeError: 向量数据库不可用
        """
        if not self._db_available or self.collection is None:
            raise RuntimeError("向量数据库不可用，无法删除文档")

        try:
            self.collection.delete(ids=[document_id])
            self.logger.info(f"文档删除成功: {document_id}")
            return True
        except Exception as e:
            self.logger.error(f"文档删除失败: {str(e)}")
            return False

    def update_document(self, document_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """更新指定文档

        Args:
            document_id: 文档ID
            content: 新内容
            metadata: 新元数据

        Returns:
            是否更新成功

        Raises:
            RuntimeError: 向量数据库不可用
        """
        if not self._db_available or self.collection is None:
            raise RuntimeError("向量数据库不可用，无法更新文档")

        try:
            # 先删除旧文档，再添加新文档
            self.collection.delete(ids=[document_id])
            embedding = self.embeddings.embed_query(content)
            self.collection.add(
                ids=[document_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            self.logger.info(f"文档更新成功: {document_id}")
            return True
        except Exception as e:
            self.logger.error(f"文档更新失败: {str(e)}")
            return False

    def search(self, query: str, top_k: int = 3) -> List[Document]:
        """执行向量检索

        Args:
            query: 查询文本
            top_k: 返回最相似的文档数量

        Returns:
            检索到的文档列表
        """
        # 确保集合存在
        try:
            self._ensure_collection_exists()
        except Exception as e:
            self.logger.error(f"确保集合存在失败: {e}")
            return []

        if not self._db_available or self.collection is None:
            return []

        try:
            query_embedding = self.embeddings.embed_query(query)

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )

            documents = []
            if results and results['documents'] and results['documents'][0]:
                for i, doc_text in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                    distance = results['distances'][0][i] if results['distances'] else 0.0
                    doc = Document(
                        page_content=doc_text,
                        metadata={**metadata, "score": distance}
                    )
                    documents.append(doc)

            return documents
        except Exception as e:
            self.logger.error(f"向量检索失败: {str(e)}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息

        Returns:
            统计信息字典
        """
        if not self._db_available or self.collection is None:
            return {"available": False}

        try:
            count = self.collection.count()
            return {
                "available": True,
                "collection_name": self._collection_name,
                "document_count": count,
                "doc_counter": self._doc_counter
            }
        except Exception as e:
            self.logger.error(f"获取集合统计失败: {str(e)}")
            return {"available": False, "error": str(e)}

    def clear_collection(self) -> bool:
        """清空集合

        Returns:
            是否清空成功
        """
        if not self._db_available or self.chroma_client is None:
            return False

        try:
            self.chroma_client.delete_collection(self._collection_name)
            self.collection = None
            self._doc_counter = 0
            self.logger.info(f"集合 {self._collection_name} 已清空")
            return True
        except Exception as e:
            self.logger.error(f"清空集合失败: {str(e)}")
            return False
