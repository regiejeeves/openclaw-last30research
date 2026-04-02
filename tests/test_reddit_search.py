"""
Tests for scripts/platform/reddit_search.py
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.platform import reddit_search


class TestRedditResult:
    def test_content_snippet_truncates_long_text(self):
        long_text = "a" * 600
        result = reddit_search.RedditResult(
            subreddit="test",
            title="Test",
            url="https://x.com",
            author="user",
            score=10,
            num_comments=5,
            created_utc=time.time(),
            selftext=long_text,
            permalink="/r/test/123",
        )
        snippet = result.content_snippet
        assert len(snippet) <= 503  # 500 + "…"
        assert snippet.endswith("…")

    def test_content_snippet_uses_title_if_no_selftext(self):
        result = reddit_search.RedditResult(
            subreddit="test",
            title="My Title Here",
            url="https://x.com",
            author="user",
            score=10,
            num_comments=5,
            created_utc=time.time(),
            selftext="",
            permalink="/r/test/123",
        )
        assert result.content_snippet == "My Title Here"

    def test_age_days_calculation(self):
        now = time.time()
        result = reddit_search.RedditResult(
            subreddit="test",
            title="Test",
            url="https://x.com",
            author="user",
            score=10,
            num_comments=5,
            created_utc=now - 86400 * 5,  # 5 days ago
            selftext="",
            permalink="/r/test/123",
        )
        assert 4.9 < result.age_days < 5.1


class TestRedditClientSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results_as_dicts(self, monkeypatch):
        """search() returns one result per subreddit searched (client searches 5 subs)."""
        mock_post = MagicMock()
        mock_post.title = "How to crack MQL5 license"
        mock_post.url = "https://reddit.com/r/MT5/comments/abc"
        mock_post.author = "crackuser"
        mock_post.score = 42
        mock_post.num_comments = 10
        mock_post.created_utc = time.time() - 86400
        mock_post.selftext = "Has anyone tried bypassing the license check?"
        mock_post.permalink = "/r/MT5/comments/abc/def"

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = [mock_post]

        mock_reddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        def fake_ensure(self):
            self._reddit = mock_reddit
            return mock_reddit

        monkeypatch.setattr(reddit_search.RedditClient, "_ensure", fake_ensure)

        client = reddit_search.RedditClient()
        # Client searches all 5 default subreddits, returns same post from each
        results = await client.search("MQL5 license", max_posts=5, max_age_days=30)

        # 5 subreddits × 1 post each
        assert len(results) == 5
        assert all(r.title == "How to crack MQL5 license" for r in results)

    @pytest.mark.asyncio
    async def test_search_filters_old_posts(self, monkeypatch):
        """Old posts (beyond max_age_days) are filtered out."""
        now = time.time()

        old_post = MagicMock()
        old_post.title = "Old Post"
        old_post.url = "https://x.com"
        old_post.author = "user"
        old_post.score = 1
        old_post.num_comments = 0
        old_post.created_utc = now - 86400 * 60  # 60 days old
        old_post.selftext = ""
        old_post.permalink = "/r/old"

        new_post = MagicMock()
        new_post.title = "New Post"
        new_post.url = "https://x.com/new"
        new_post.author = "user"
        new_post.score = 5
        new_post.num_comments = 2
        new_post.created_utc = now - 86400 * 5  # 5 days old
        new_post.selftext = "New content"
        new_post.permalink = "/r/new"

        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = [old_post, new_post]

        mock_reddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        def fake_ensure(self):
            self._reddit = mock_reddit
            return mock_reddit

        monkeypatch.setattr(reddit_search.RedditClient, "_ensure", fake_ensure)

        client = reddit_search.RedditClient()
        # Searches all 5 subs; each sub returns [old_post, new_post]
        # Only new_post is within 30 days, so 5 subs × 1 new_post = 5 results
        results = await client.search("test", max_posts=10, max_age_days=30)

        assert len(results) == 5  # 5 subs × 1 new post each (old filtered)
        assert all(r.title == "New Post" for r in results)


class TestModuleSearch:
    @pytest.mark.asyncio
    async def test_module_search_delegates_to_client(self, monkeypatch):
        """Module-level search() returns dicts with expected keys."""
        client_results = [
            {
                "title": "Found it",
                "url": "https://x.com",
                "author": "u",
                "score": 1,
                "num_comments": 0,
                "created_utc": time.time(),
                "content": "...",
                "permalink": "/r/test/1",
                "subreddit": "test",
                "platform": "reddit",
            }
        ]

        async def mock_client_search(self, query, subreddits, max_posts, max_age_days):
            return client_results

        monkeypatch.setattr(reddit_search.RedditClient, "search", mock_client_search)

        results = await reddit_search.search("test query")

        assert len(results) == 1
        assert results[0]["title"] == "Found it"
        assert results[0]["platform"] == "reddit"

    @pytest.mark.asyncio
    async def test_gather_searches_runs_parallel(self, monkeypatch):
        """gather_searches runs multiple queries concurrently."""
        call_count = 0

        async def mock_search(query, subreddits, max_posts, max_age_days):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return [{"title": f"Result for {query}", "url": "https://x.com",
                     "author": "u", "score": 1, "num_comments": 0,
                     "created_utc": time.time(), "content": "...", "platform": "reddit",
                     "permalink": "/r/test/1", "subreddit": "test"}]

        monkeypatch.setattr(reddit_search, "search", mock_search)

        results = await reddit_search.gather_searches(["q1", "q2", "q3"])

        assert len(results) == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_gather_searches_empty_input(self):
        """Empty list returns empty list."""
        results = await reddit_search.gather_searches([])
        assert results == []
