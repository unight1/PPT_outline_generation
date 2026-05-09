from unittest.mock import MagicMock, patch

import pytest

from app.retrieval.sources.fake_web import FakeWebSearchProvider
from app.retrieval.types import RetrievalHit


class TestFakeWebSearchProvider:
    def test_default_results(self):
        provider = FakeWebSearchProvider()
        results = provider.search("test query", max_results=5)
        assert len(results) == 1
        assert isinstance(results[0], RetrievalHit)
        assert results[0].source_id == "https://example.com/fake-result"

    def test_custom_results(self):
        custom = [
            RetrievalHit(snippet="result 1", source_id="url1", locator="t1", score=0.9),
            RetrievalHit(snippet="result 2", source_id="url2", locator="t2", score=0.7),
            RetrievalHit(snippet="result 3", source_id="url3", locator="t3", score=0.5),
        ]
        provider = FakeWebSearchProvider(results=custom)
        results = provider.search("test", max_results=2)
        assert len(results) == 2
        assert results[0].snippet == "result 1"

    def test_max_results_caps_output(self):
        provider = FakeWebSearchProvider()
        results = provider.search("test", max_results=0)
        assert results == []


class TestTavilySearchProvider:
    @patch("tavily.TavilyClient")
    def test_search_returns_hits(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "content": "AI is transforming education.",
                    "url": "https://example.com/ai-edu",
                    "title": "AI in Education",
                    "score": 0.92,
                },
                {
                    "content": "Machine learning applications.",
                    "url": "https://example.com/ml",
                    "title": "ML Applications",
                    "score": 0.78,
                },
            ]
        }
        mock_client_cls.return_value = mock_client

        from app.retrieval.sources.tavily import TavilySearchProvider
        provider = TavilySearchProvider(api_key="test-key")
        results = provider.search("artificial intelligence", max_results=5)

        assert len(results) == 2
        assert results[0].snippet == "AI is transforming education."
        assert results[0].source_id == "https://example.com/ai-edu"
        assert results[0].locator == "AI in Education"
        assert results[0].score == 0.92

    @patch("tavily.TavilyClient")
    def test_search_skips_empty_content(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {"content": "valid content", "url": "https://example.com", "title": "T", "score": 0.8},
                {"content": "", "url": "https://example.com/empty", "title": "Empty", "score": 0.5},
                {"content": "  ", "url": "https://example.com/ws", "title": "WS", "score": 0.4},
            ]
        }
        mock_client_cls.return_value = mock_client

        from app.retrieval.sources.tavily import TavilySearchProvider
        provider = TavilySearchProvider(api_key="test-key")
        results = provider.search("test", max_results=5)
        assert len(results) == 1

    @patch("tavily.TavilyClient")
    def test_search_returns_empty_on_api_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        from app.retrieval.sources.tavily import TavilySearchProvider
        provider = TavilySearchProvider(api_key="test-key")
        results = provider.search("test", max_results=5)
        assert results == []
