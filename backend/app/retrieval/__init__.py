from app.retrieval.types import (
    RetrievalDepth,
    RetrievalHit,
    RetrievalRequest,
    RetrievalResult,
)
from app.retrieval.retriever import CoreRetriever
from app.retrieval.sources.local import LocalFileLoader
from app.retrieval.embedding.fake import FakeEmbeddingProvider
from app.retrieval.index.chroma import ChromaVectorIndex
from app.retrieval.reranker.fake import FakeReranker
from app.retrieval.sources.tavily import TavilySearchProvider

try:
    from app.retrieval.embedding.bge import BGEEmbeddingProvider
except Exception:  # pragma: no cover - environment dependent
    BGEEmbeddingProvider = None  # type: ignore[assignment]

try:
    from app.retrieval.reranker.bge import BGEReranker
except Exception:  # pragma: no cover - environment dependent
    BGEReranker = None  # type: ignore[assignment]

__all__ = [
    "CoreRetriever",
    "RetrievalDepth",
    "RetrievalHit",
    "RetrievalRequest",
    "RetrievalResult",
    "get_retriever",
]

_retriever: CoreRetriever | None = None
_retriever_config: tuple[str, str, str] | None = None


def get_retriever(
    documents_dir: str = "",
    embedding_dimension: int = 128,
    chroma_persist_dir: str = "./chroma_data",
    tavily_api_key: str = "",
) -> CoreRetriever:
    """获取或创建单例 CoreRetriever。

    Args:
        documents_dir: 文档目录路径。
        embedding_dimension: 向量维度。
        chroma_persist_dir: ChromaDB 持久化目录。
    """
    global _retriever, _retriever_config
    normalized_docs_dir = documents_dir or "."
    normalized_chroma_dir = chroma_persist_dir or "./chroma_data"
    normalized_tavily_key = tavily_api_key or ""
    current_config = (normalized_docs_dir, normalized_chroma_dir, normalized_tavily_key)

    # Rebuild singleton when retrieval inputs change (especially Tavily key enable/disable).
    if _retriever is None or _retriever_config != current_config:
        loader = LocalFileLoader(documents_dir) if documents_dir else LocalFileLoader(".")
        if BGEEmbeddingProvider is not None:
            embedding = BGEEmbeddingProvider()
        else:
            embedding = FakeEmbeddingProvider(dimension=embedding_dimension)
        index = ChromaVectorIndex(persist_dir=chroma_persist_dir)
        if BGEReranker is not None:
            reranker = BGEReranker()
        else:
            reranker = FakeReranker()
        web_search = TavilySearchProvider(normalized_tavily_key) if normalized_tavily_key else None
        _retriever = CoreRetriever(
            loader=loader,
            embedding=embedding,
            index=index,
            reranker=reranker,
            web_search=web_search,
        )
        _retriever_config = current_config
    return _retriever
