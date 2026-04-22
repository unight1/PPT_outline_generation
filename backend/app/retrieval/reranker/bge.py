import numpy as np
from sentence_transformers import CrossEncoder

from app.retrieval.interfaces import Reranker
from app.retrieval.types import RetrievalHit


class BGEReranker(Reranker):
    """基于 BGE 的重排序器。"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        """对候选文本进行重排序，返回按相关度排序的 top_k 结果。"""
        if not hits:
            return []

        pairs = [(query, hit.snippet) for hit in hits]
        scores = self._model.predict(pairs)

        ranked = sorted(
            zip(scores, hits),
            key=lambda x: x[0],
            reverse=True,
        )

        return [
            RetrievalHit(
                snippet=hit.snippet,
                source_id=hit.source_id,
                locator=hit.locator,
                score=float(score),
                confidence=hit.confidence,
            )
            for score, hit in ranked[:top_k]
        ]
