from pathlib import Path

from app.retrieval.index.chroma import ChromaVectorIndex
from app.retrieval.types import DocumentChunk


def _make_chunks(n: int) -> list[DocumentChunk]:
    return [
        DocumentChunk(content=f"chunk content number {i}", source_id="doc.md", locator=f"L{i}")
        for i in range(n)
    ]


def test_not_built_initially(tmp_path: Path):
    idx = ChromaVectorIndex(persist_dir=str(tmp_path / "chroma"))
    assert idx.is_built is False


def test_build_and_query(tmp_path: Path):
    idx = ChromaVectorIndex(persist_dir=str(tmp_path / "chroma"))
    chunks = _make_chunks(5)
    # 单位向量，每个 chunk 的向量只在对应维度为 1
    embeddings = [[float(i == j) for j in range(5)] for i in range(5)]
    idx.build(chunks, embeddings)
    assert idx.is_built

    results = idx.query([1.0, 0.0, 0.0, 0.0, 0.0], top_k=3)
    assert len(results) == 3
    assert results[0].chunk_index == 0
    assert results[0].score > 0.9


def test_persistence(tmp_path: Path):
    persist_dir = str(tmp_path / "chroma")

    # 第一次写入
    idx1 = ChromaVectorIndex(persist_dir=persist_dir)
    chunks = _make_chunks(3)
    embeddings = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    idx1.build(chunks, embeddings)

    # 第二次读取（新实例）
    idx2 = ChromaVectorIndex(persist_dir=persist_dir)
    assert idx2.is_built
    results = idx2.query([0.0, 1.0], top_k=2)
    assert len(results) == 2


def test_top_k_larger_than_index(tmp_path: Path):
    idx = ChromaVectorIndex(persist_dir=str(tmp_path / "chroma"))
    chunks = _make_chunks(3)
    embeddings = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    idx.build(chunks, embeddings)
    results = idx.query([1.0, 0.0], top_k=10)
    assert len(results) == 3


def test_empty_build(tmp_path: Path):
    idx = ChromaVectorIndex(persist_dir=str(tmp_path / "chroma"))
    idx.build([], [])
    results = idx.query([1.0], top_k=5)
    assert results == []


def test_query_not_built(tmp_path: Path):
    idx = ChromaVectorIndex(persist_dir=str(tmp_path / "chroma"))
    results = idx.query([1.0, 0.0], top_k=5)
    assert results == []
