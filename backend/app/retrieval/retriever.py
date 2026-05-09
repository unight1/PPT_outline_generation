import asyncio
import logging
import time

from tenacity import retry, stop_after_attempt, wait_exponential

from app.retrieval.depth_config import get_depth_profile
from app.retrieval.interfaces import (
    DocumentLoader,
    EmbeddingProvider,
    Reranker,
    VectorIndex,
    WebSearchProvider,
)
from app.retrieval.types import RetrievalHit, RetrievalRequest, RetrievalResult

logger = logging.getLogger(__name__)


class CoreRetriever:
    """核心检索编排器：loader → embed → index → query → web search → merge → rerank。"""

    def __init__(
        self,
        loader: DocumentLoader,
        embedding: EmbeddingProvider,
        index: VectorIndex,
        reranker: Reranker,
        web_search: WebSearchProvider | None = None,
    ) -> None:
        self._loader = loader
        self._embedding = embedding
        self._index = index
        self._reranker = reranker
        self._web_search = web_search
        self._chunks: list | None = None

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        profile = get_depth_profile(request.depth)
        start = time.monotonic()

        try:
            hits = await asyncio.wait_for(
                self._retrieve_inner(request, profile),
                timeout=profile.timeout_seconds,
            )
        except asyncio.TimeoutError:
            hits = []

        latency = (time.monotonic() - start) * 1000
        return RetrievalResult(hits=hits, depth=request.depth, latency_ms=latency)

    async def _retrieve_inner(self, request, profile):
        await self._ensure_index()

        local_hits = await self._local_search(request, profile)

        web_hits: list[RetrievalHit] = []
        if profile.enable_web_search:
            if self._web_search is not None:
                web_hits = await self._web_search_async(
                    request.query, profile.web_search_max_results,
                )
                logger.info("Web search returned %d hits for query: %s", len(web_hits), request.query[:60])
            else:
                logger.warning("Web search enabled (depth=%s) but no WebSearchProvider configured", request.depth)

        max_results = request.max_results or profile.max_recall
        if profile.enable_web_search and web_hits:
            web_cap = min(profile.web_search_max_results, len(web_hits))
            local_cap = max(max_results - web_cap, 0)
            local_hits = local_hits[:local_cap]

        merged = self._merge_hits(local_hits, web_hits)
        merged = merged[:max_results]

        if profile.enable_reranking:
            merged = self._reranker.rerank(request.query, merged, profile.rerank_top_k)

        return merged

    async def _local_search(self, request, profile):
        query_vec = self._embed_query(request.query)
        top_k = request.max_results or profile.max_recall
        matches = self._index.query(query_vec, top_k=top_k)

        hits = self._matches_to_hits(matches)
        hits = [h for h in hits if h.score is None or h.score >= profile.min_score_threshold]

        if request.source_filter:
            hits = [h for h in hits if h.source_id in request.source_filter]
        return hits

    async def _web_search_async(self, query: str, max_results: int) -> list[RetrievalHit]:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._web_search.search, query, max_results)
        except Exception:
            logger.warning("Web search failed for query: %s", query[:80], exc_info=True)
            return []

    @staticmethod
    def _merge_hits(local: list[RetrievalHit], web: list[RetrievalHit]) -> list[RetrievalHit]:
        seen: set[str] = set()
        merged: list[RetrievalHit] = []
        for hit in local + web:
            key = hit.snippet[:100]
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
        return merged

    async def _ensure_index(self) -> None:
        if self._index.is_built:
            if self._chunks is None:
                self._chunks = self._loader.load()
            return
        chunks = self._loader.load()
        texts = [c.content for c in chunks]
        embeddings = self._embed_texts(texts)
        self._index.build(chunks, embeddings)
        self._chunks = chunks

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=2))
    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._embedding.embed_texts(texts)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=2))
    def _embed_query(self, query: str) -> list[float]:
        return self._embedding.embed_query(query)

    def _matches_to_hits(self, matches) -> list[RetrievalHit]:
        chunks = self._chunks or []
        hits: list[RetrievalHit] = []
        for m in matches:
            if m.chunk_index < len(chunks):
                chunk = chunks[m.chunk_index]
                hits.append(
                    RetrievalHit(
                        snippet=chunk.content,
                        source_id=chunk.source_id,
                        locator=chunk.locator,
                        score=m.score,
                    )
                )
        return hits
