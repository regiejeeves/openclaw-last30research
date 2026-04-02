"""
Tests for scripts/platform/tavily_search.py
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.platform import tavily_search


class TestDaysToTimeRange:
    def test_day_1(self):
        assert tavily_search._days_to_timerange(1) == "day"

    def test_week(self):
        assert tavily_search._days_to_timerange(7) == "week"

    def test_month(self):
        assert tavily_search._days_to_timerange(30) == "month"

    def test_year(self):
        assert tavily_search._days_to_timerange(90) == "year"

    def test_month_boundary(self):
        # 8 days is > 7 so it falls into month range
        assert tavily_search._days_to_timerange(8) == "month"
        assert tavily_search._days_to_timerange(15) == "month"


class TestDepthMapping:
    def test_all_depths(self):
        assert tavily_search._depth_to_search_depth("ultra-fast") == "ultra-fast"
        assert tavily_search._depth_to_search_depth("fast") == "fast"
        assert tavily_search._depth_to_search_depth("basic") == "basic"
        assert tavily_search._depth_to_search_depth("advanced") == "advanced"

    def test_unknown_defaults_to_basic(self):
        assert tavily_search._depth_to_search_depth("invalid") == "basic"
        assert tavily_search._depth_to_search_depth("") == "basic"


class TestSearchNoApiKey:
    def test_returns_empty_when_no_api_key(self, monkeypatch):
        """When TAVILY_API_KEY is not set, search() returns [] immediately."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        # Patch the module-level _API_KEY to empty
        monkeypatch.setattr(tavily_search, "_API_KEY", "")

        result = asyncio.run(tavily_search.search("test query"))
        assert result == []


class TestSearchWithMock:
    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self, monkeypatch):
        """Tavily returns structured results with expected keys."""
        monkeypatch.setattr(tavily_search, "_API_KEY", "fake-key")

        mock_response = {
            "results": [
                {
                    "title": "Test Post",
                    "url": "https://example.com/post",
                    "content": "This is test content about MQL5 cracking.",
                    "score": 0.95,
                    "published_date": "2026-04-01",
                },
                {
                    "title": "Another Post",
                    "url": "https://example.com/another",
                    "content": "More content here.",
                    "score": 0.88,
                    "published_date": None,
                },
            ]
        }

        mock_api = MagicMock()
        mock_api.search.return_value = mock_response
        monkeypatch.setattr(tavily_search, "TavilySearchAPI", lambda api_key: mock_api)

        results = await tavily_search.search("mql5 cracking")

        assert len(results) == 2
        assert results[0]["title"] == "Test Post"
        assert results[0]["url"] == "https://example.com/post"
        assert results[0]["score"] == 0.95
        assert results[0]["platform"] == "web"
        assert results[1]["published_date"] is None

    @pytest.mark.asyncio
    async def test_gather_searches_flattens_results(self, monkeypatch):
        """gather_searches returns a flat list from multiple queries."""
        monkeypatch.setattr(tavily_search, "_API_KEY", "fake-key")

        mock_response = {"results": [{"title": f"Result {i}", "url": f"https://x.com/{i}",
                                      "content": "...", "score": 0.9, "published_date": None}
                                     for i in range(3)]}

        mock_api = MagicMock()
        mock_api.search.return_value = mock_response
        monkeypatch.setattr(tavily_search, "TavilySearchAPI", lambda api_key: mock_api)

        results = await tavily_search.gather_searches(["query A", "query B"])

        assert len(results) == 6  # 3 per query × 2 queries

    @pytest.mark.asyncio
    async def test_gather_searches_empty_queries(self):
        """Empty query list returns empty result."""
        results = await tavily_search.gather_searches([])
        assert results == []

    @pytest.mark.asyncio
    async def test_search_timeout_retries(self, monkeypatch):
        """On timeout, search retries up to 3 times."""
        monkeypatch.setattr(tavily_search, "_API_KEY", "fake-key")
        import httpx
        mock_api = MagicMock()
        mock_api.search.side_effect = [
            httpx.TimeoutException("timeout"),
            httpx.TimeoutException("timeout"),
            {"results": [{"title": "Success", "url": "https://x.com",
                          "content": "...", "score": 0.9, "published_date": None}],
             },
        ]
        monkeypatch.setattr(tavily_search, "TavilySearchAPI", lambda api_key: mock_api)

        results = await tavily_search.search("test")
        assert len(results) == 1
        assert mock_api.search.call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_search_all_retries_fail_returns_empty(self, monkeypatch):
        """If all retries fail, search returns [] without crashing."""
        monkeypatch.setattr(tavily_search, "_API_KEY", "fake-key")
        import httpx
        mock_api = MagicMock()
        mock_api.search.side_effect = httpx.TimeoutException("persistent timeout")
        monkeypatch.setattr(tavily_search, "TavilySearchAPI", lambda api_key: mock_api)

        results = await tavily_search.search("test")
        assert results == []
