from app.retrieval.interfaces import WebSearchProvider
from app.retrieval.types import RetrievalHit


class FakeWebSearchProvider(WebSearchProvider):
    """测试用占位网络搜索提供者。"""

    def __init__(self, results: list[RetrievalHit] | None = None) -> None:
        self._results = results or [
            RetrievalHit(
                snippet="这是一个来自网络的搜索结果片段。",
                source_id="https://example.com/fake-result",
                locator="示例页面标题",
                score=0.85,
            ),
        ]

    def search(self, query: str, max_results: int) -> list[RetrievalHit]:
        return self._results[:max_results]
