from abc import ABC, abstractmethod

from app.retrieval.types import DocumentChunk, IndexMatch, RetrievalHit


class DocumentLoader(ABC):
    """文档加载器抽象基类。"""

    @abstractmethod
    def load(self) -> list[DocumentChunk]:
        ...


class EmbeddingProvider(ABC):
    """向量嵌入提供者抽象基类。"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        ...


class VectorIndex(ABC):
    """向量索引抽象基类。"""

    @property
    @abstractmethod
    def is_built(self) -> bool:
        ...

    @abstractmethod
    def build(
        self, chunks: list[DocumentChunk], embeddings: list[list[float]]
    ) -> None:
        ...

    @abstractmethod
    def query(
        self, query_embedding: list[float], top_k: int
    ) -> list[IndexMatch]:
        ...


class Reranker(ABC):
    """重排器抽象基类。"""

    @abstractmethod
    def rerank(
        self, query: str, hits: list[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        ...


class WebSearchProvider(ABC):
    """外部网络搜索提供者抽象基类。"""

    @abstractmethod
    def search(self, query: str, max_results: int) -> list[RetrievalHit]:
        ...
