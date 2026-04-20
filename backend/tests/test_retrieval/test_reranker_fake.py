from app.retrieval.reranker.fake import FakeReranker
from app.retrieval.types import RetrievalHit


def _make_hits(n: int) -> list[RetrievalHit]:
    return [
        RetrievalHit(snippet=f"hit {i}", source_id="doc.md", locator=f"L{i}", score=0.9 - i * 0.1)
        for i in range(n)
    ]


def test_passthrough():
    reranker = FakeReranker()
    hits = _make_hits(5)
    result = reranker.rerank("query", hits, top_k=10)
    assert len(result) == 5
    assert result == hits


def test_top_k_truncation():
    reranker = FakeReranker()
    hits = _make_hits(10)
    result = reranker.rerank("query", hits, top_k=3)
    assert len(result) == 3


def test_empty_input():
    reranker = FakeReranker()
    result = reranker.rerank("query", [], top_k=5)
    assert result == []
