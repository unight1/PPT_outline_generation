from __future__ import annotations

import uuid
from pathlib import Path

import chromadb

from app.retrieval.interfaces import VectorIndex
from app.retrieval.types import DocumentChunk, IndexMatch

_COLLECTION_NAME = "rag_chunks"


class ChromaVectorIndex(VectorIndex):
    """基于 ChromaDB 的持久化向量索引。"""

    def __init__(self, persist_dir: str = "./chroma_data") -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection: chromadb.Collection | None = None
        self._chunks: list[DocumentChunk] = []

    @property
    def is_built(self) -> bool:
        try:
            self._client.get_collection(_COLLECTION_NAME)
            return True
        except Exception:
            return False

    def build(
        self, chunks: list[DocumentChunk], embeddings: list[list[float]]
    ) -> None:
        if not chunks or not embeddings:
            return

        try:
            self._client.delete_collection(_COLLECTION_NAME)
        except Exception:
            pass

        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [
            {"source_id": c.source_id, "locator": c.locator}
            for c in chunks
        ]

        batch_size = 500
        for i in range(0, len(chunks), batch_size):
            end = i + batch_size
            self._collection.add(
                ids=ids[i:end],
                documents=[c.content for c in chunks[i:end]],
                embeddings=list(embeddings[i:end]),  # type: ignore[arg-type]
                metadatas=metadatas[i:end],  # type: ignore[arg-type]
            )

        self._chunks = chunks

    def query(
        self, query_embedding: list[float], top_k: int
    ) -> list[IndexMatch]:
        collection = self._get_collection()
        if collection is None:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()) or 1,
            include=["documents", "metadatas", "distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        documents = results["documents"][0] if results["documents"] else []
        distances = results["distances"][0] if results["distances"] else []

        # ChromaDB cosine distance → similarity: score = 1 - distance
        matches: list[IndexMatch] = []
        for i, doc_text in enumerate(documents):
            idx = self._find_chunk_index(doc_text)
            distance = distances[i] if i < len(distances) else 0.0
            matches.append(
                IndexMatch(
                    chunk_index=idx,
                    score=1.0 - distance,
                )
            )
        return matches

    def _get_collection(self) -> chromadb.Collection | None:
        if self._collection is not None:
            return self._collection
        try:
            self._collection = self._client.get_collection(_COLLECTION_NAME)
            return self._collection
        except Exception:
            return None

    def _find_chunk_index(self, content: str) -> int:
        for i, chunk in enumerate(self._chunks):
            if chunk.content == content:
                return i
        # 如果 chunks 还没加载，尝试从 collection 恢复
        if not self._chunks:
            self._load_chunks_from_collection()
            for i, chunk in enumerate(self._chunks):
                if chunk.content == content:
                    return i
        return 0

    def _load_chunks_from_collection(self) -> None:
        collection = self._get_collection()
        if collection is None:
            return
        count = collection.count()
        if count == 0:
            return
        results = collection.get(
            include=["documents", "metadatas"],
        )
        docs = results["documents"] or []
        metas = results["metadatas"] or []
        self._chunks = [
            DocumentChunk(
                content=doc,
                source_id=str(meta.get("source_id", "")),
                locator=str(meta.get("locator", "")),
            )
            for doc, meta in zip(docs, metas)
        ]
