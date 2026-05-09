import asyncio
from pathlib import Path

import pytest

from app.retrieval import CoreRetriever, RetrievalDepth, RetrievalRequest
from app.retrieval.embedding.fake import FakeEmbeddingProvider
from app.retrieval.index.chroma import ChromaVectorIndex
from app.retrieval.reranker.fake import FakeReranker
from app.retrieval.sources.fake_web import FakeWebSearchProvider
from app.retrieval.sources.local import LocalFileLoader
from app.retrieval.types import RetrievalHit


def _make_retriever(docs_dir: Path, chroma_dir: Path, web_search=None) -> CoreRetriever:
    loader = LocalFileLoader(docs_dir)
    embedding = FakeEmbeddingProvider(dimension=64)
    index = ChromaVectorIndex(persist_dir=str(chroma_dir))
    reranker = FakeReranker()
    return CoreRetriever(loader=loader, embedding=embedding, index=index, reranker=reranker, web_search=web_search)


@pytest.mark.anyio
async def test_retrieve_l0(sample_docs_dir: Path, tmp_path: Path):
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c1")
    result = await retriever.retrieve(
        RetrievalRequest(query="PPT大纲", depth=RetrievalDepth.L0)
    )
    assert result.depth == RetrievalDepth.L0
    assert result.latency_ms >= 0
    assert isinstance(result.hits, list)


@pytest.mark.anyio
async def test_retrieve_l2(sample_docs_dir: Path, tmp_path: Path):
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c2")
    result = await retriever.retrieve(
        RetrievalRequest(query="技术方案", depth=RetrievalDepth.L2)
    )
    assert result.depth == RetrievalDepth.L2
    for hit in result.hits:
        assert hit.snippet
        assert hit.source_id
        assert hit.locator


@pytest.mark.anyio
async def test_source_filter(sample_docs_dir: Path, tmp_path: Path):
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c3")
    result = await retriever.retrieve(
        RetrievalRequest(query="系统", source_filter=["intro.md"])
    )
    for hit in result.hits:
        assert hit.source_id == "intro.md"


@pytest.mark.anyio
async def test_empty_dir_returns_no_hits(empty_docs_dir: Path, tmp_path: Path):
    retriever = _make_retriever(empty_docs_dir, tmp_path / "c4")
    result = await retriever.retrieve(RetrievalRequest(query="test"))
    assert result.hits == []


@pytest.mark.anyio
async def test_l0_fewer_than_l2(sample_docs_dir: Path, tmp_path: Path):
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c5")
    r0 = await retriever.retrieve(RetrievalRequest(query="系统", depth=RetrievalDepth.L0))
    retriever2 = _make_retriever(sample_docs_dir, tmp_path / "c6")
    r2 = await retriever2.retrieve(RetrievalRequest(query="系统", depth=RetrievalDepth.L2))
    assert len(r0.hits) <= len(r2.hits)


@pytest.mark.anyio
async def test_result_serializable(sample_docs_dir: Path, tmp_path: Path):
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c7")
    result = await retriever.retrieve(RetrievalRequest(query="test"))
    data = result.model_dump()
    assert "hits" in data
    assert "depth" in data
    assert "latency_ms" in data


@pytest.mark.anyio
async def test_web_search_merged_into_results(sample_docs_dir: Path, tmp_path: Path):
    web = FakeWebSearchProvider(results=[
        RetrievalHit(snippet="web result about PPT", source_id="https://web.example.com/ppt", locator="Web Title", score=0.9),
    ])
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c8", web_search=web)
    result = await retriever.retrieve(RetrievalRequest(query="PPT", depth=RetrievalDepth.L1))
    web_hits = [h for h in result.hits if h.source_id.startswith("https://")]
    assert len(web_hits) >= 1


@pytest.mark.anyio
async def test_web_search_not_used_in_l0(sample_docs_dir: Path, tmp_path: Path):
    web = FakeWebSearchProvider(results=[
        RetrievalHit(snippet="should not appear", source_id="https://web.example.com", locator="T", score=0.9),
    ])
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c9", web_search=web)
    result = await retriever.retrieve(RetrievalRequest(query="PPT", depth=RetrievalDepth.L0))
    web_hits = [h for h in result.hits if h.source_id.startswith("https://")]
    assert len(web_hits) == 0


@pytest.mark.anyio
async def test_web_search_graceful_degradation(sample_docs_dir: Path, tmp_path: Path):
    class FailingWebSearch:
        def search(self, query, max_results):
            raise RuntimeError("API down")
    retriever = _make_retriever(sample_docs_dir, tmp_path / "c10", web_search=FailingWebSearch())
    result = await retriever.retrieve(RetrievalRequest(query="PPT", depth=RetrievalDepth.L1))
    assert isinstance(result.hits, list)
