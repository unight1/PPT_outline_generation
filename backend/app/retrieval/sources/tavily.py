import logging

from app.retrieval.interfaces import WebSearchProvider
from app.retrieval.types import RetrievalHit

logger = logging.getLogger(__name__)


class TavilySearchProvider(WebSearchProvider):
    """基于 Tavily Search API 的网络搜索提供者。"""

    def __init__(self, api_key: str, search_depth: str = "advanced") -> None:
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=api_key)
        self._search_depth = search_depth

    def search(self, query: str, max_results: int) -> list[RetrievalHit]:
        try:
            response = self._client.search(
                query,
                max_results=max_results,
                search_depth=self._search_depth,
            )
        except Exception:
            logger.warning("Tavily search failed for query: %s", query[:80], exc_info=True)
            return []

        hits: list[RetrievalHit] = []
        for r in response.get("results", []):
            content = r.get("content") or ""
            if not content.strip():
                continue
            hits.append(
                RetrievalHit(
                    snippet=content,
                    source_id=r.get("url") or "",
                    locator=r.get("title") or "",
                    score=r.get("score"),
                )
            )
        return hits
