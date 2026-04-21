import os
from app.retrieval.interfaces import EmbeddingProvider

DIMENSION = 512

class BGEEmbeddingProvider(EmbeddingProvider):
    """BGE 向量嵌入提供者。"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.prompt = "为这个句子生成表示以用于检索相关文章："

    @property
    def dimension(self) -> int:
        return DIMENSION

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).tolist()

    def embed_query(self, query: str) -> list[float]:
        return self._model.encode([self.prompt + query], convert_to_numpy=True, normalize_embeddings=True)[0].tolist()