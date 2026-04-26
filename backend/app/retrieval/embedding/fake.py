import hashlib

import numpy as np

from app.retrieval.interfaces import EmbeddingProvider

_FAKE_DIMENSION = 128


class FakeEmbeddingProvider(EmbeddingProvider):
    """基于确定性哈希的伪嵌入提供者，用于开发和测试。"""

    def __init__(self, dimension: int = _FAKE_DIMENSION) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._hash_embed(query)

    def _hash_embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.default_rng(
            seed=int.from_bytes(digest[:8], "little", signed=False)
        )
        vec = rng.standard_normal(self._dimension).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()
