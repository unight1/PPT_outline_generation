from app.retrieval.interfaces import Reranker
from app.retrieval.types import RetrievalHit


class FakeReranker(Reranker):
    """直通重排器，原样返回输入结果（截取 top_k）。"""

    def rerank(
        self, query: str, hits: list[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        return hits[:top_k]
