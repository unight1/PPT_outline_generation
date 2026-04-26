from app.retrieval.types import (
    RetrievalDepth,
    RetrievalHit,
    RetrievalRequest,
    RetrievalResult,
)


def test_retrieval_depth_values():
    assert RetrievalDepth.L0 == "L0"
    assert RetrievalDepth.L1 == "L1"
    assert RetrievalDepth.L2 == "L2"
    assert len(RetrievalDepth) == 3


def test_retrieval_hit_minimal():
    hit = RetrievalHit(snippet="hello", source_id="doc.md", locator="L1-L2")
    assert hit.snippet == "hello"
    assert hit.score is None
    assert hit.confidence is None


def test_retrieval_hit_full():
    hit = RetrievalHit(
        snippet="text", source_id="a.md", locator="L5", score=0.85, confidence=0.9
    )
    assert hit.score == 0.85
    assert hit.confidence == 0.9


def test_retrieval_request_defaults():
    req = RetrievalRequest(query="test")
    assert req.depth == RetrievalDepth.L1
    assert req.source_filter is None
    assert req.max_results is None


def test_retrieval_result():
    hit = RetrievalHit(snippet="s", source_id="d", locator="L1")
    result = RetrievalResult(hits=[hit], depth=RetrievalDepth.L0, latency_ms=12.5)
    assert len(result.hits) == 1
    assert result.latency_ms == 12.5


def test_hit_serialization():
    hit = RetrievalHit(snippet="片段", source_id="f.md", locator="L3-L5", score=0.7)
    data = hit.model_dump()
    assert data["snippet"] == "片段"
    assert data["source_id"] == "f.md"
    assert data["locator"] == "L3-L5"
    assert data["score"] == 0.7
