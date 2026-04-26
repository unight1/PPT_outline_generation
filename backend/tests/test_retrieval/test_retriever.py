import asyncio
from pathlib import Path

import pytest

from app.retrieval import CoreRetriever, RetrievalDepth, RetrievalRequest
from app.retrieval.embedding.fake import FakeEmbeddingProvider
from app.retrieval.index.chroma import ChromaVectorIndex
from app.retrieval.reranker.fake import FakeReranker
from app.retrieval.sources.local import LocalFileLoader


def _make_retriever(docs_dir: Path, chroma_dir: Path) -> CoreRetriever:
    loader = LocalFileLoader(docs_dir)
    embedding = FakeEmbeddingProvider(dimension=64)
    index = ChromaVectorIndex(persist_dir=str(chroma_dir))
    reranker = FakeReranker()
    return CoreRetriever(loader=loader, embedding=embedding, index=index, reranker=reranker)


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
