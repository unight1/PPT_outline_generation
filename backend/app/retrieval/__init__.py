from app.retrieval.types import (
    RetrievalDepth,
    RetrievalHit,
    RetrievalRequest,
    RetrievalResult,
)
from app.retrieval.retriever import CoreRetriever
from app.retrieval.sources.local import LocalFileLoader
from app.retrieval.embedding.fake import FakeEmbeddingProvider
from app.retrieval.embedding.bge import BGEEmbeddingProvider
from app.retrieval.index.chroma import ChromaVectorIndex
from app.retrieval.reranker.fake import FakeReranker

__all__ = [
    "CoreRetriever",
    "RetrievalDepth",
    "RetrievalHit",
    "RetrievalRequest",
    "RetrievalResult",
    "get_retriever",
]

_retriever: CoreRetriever | None = None


def get_retriever(
    documents_dir: str = "",
    embedding_dimension: int = 128,
    chroma_persist_dir: str = "./chroma_data",
) -> CoreRetriever:
    """获取或创建单例 CoreRetriever。

    Args:
        documents_dir: 文档目录路径。
        embedding_dimension: 向量维度。
        chroma_persist_dir: ChromaDB 持久化目录。
    """
    global _retriever
    if _retriever is None:
        loader = LocalFileLoader(documents_dir) if documents_dir else LocalFileLoader(".")
        embedding =BGEEmbeddingProvider()
        index = ChromaVectorIndex(persist_dir=chroma_persist_dir)
        reranker = FakeReranker()
        _retriever = CoreRetriever(
            loader=loader,
            embedding=embedding,
            index=index,
            reranker=reranker,
        )
    return _retriever
