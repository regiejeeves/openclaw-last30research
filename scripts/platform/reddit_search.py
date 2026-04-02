"""
Reddit search via PRAW (Python Reddit API Wrapper).
Read-only access — no authentication required for public subreddits.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
USER_AGENT = "last30research/1.0 (research tool; contact: owner)"
SUBREDDITS = ["MT5", "metatrader", "algotrading", "forex", "quant"]
MAX_POSTS_PER_SUB = 20

# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class RedditResult:
    subreddit: str
    title: str
    url: str
    author: str
    score: int
    num_comments: int
    created_utc: float
    selftext: str
    permalink: str
    platform: str = "reddit"

    @property
    def content_snippet(self) -> str:
        text = self.selftext or self.title
        return text[:500] + "…" if len(text) > 500 else text

    @property
    def age_days(self) -> float:
        now = datetime.now(timezone.utc).timestamp()
        return (now - self.created_utc) / 86400


# ── PRAW lazy wrapper ─────────────────────────────────────────────────────────

class RedditClient:
    """Lightweight PRAW wrapper that initialises the client on first use."""

    def __init__(self) -> None:
        self._reddit: Optional[Any] = None

    def _ensure(self) -> Any:
        if self._reddit is None:
            if not CLIENT_ID or not CLIENT_SECRET:
                raise RuntimeError(
                    "Reddit: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set. "
                    "See: https://www.reddit.com/prefs/apps"
                )
            try:
                import praw
            except ImportError:
                raise RuntimeError(
                    "praw not installed — run: uv add praw"
                )
            self._reddit = praw.Reddit(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                user_agent=USER_AGENT,
                read_only=True,
            )
        return self._reddit

    async def search(
        self,
        query: str,
        subreddits: Optional[List[str]] = None,
        max_posts: int = MAX_POSTS_PER_SUB,
        max_age_days: int = 30,
    ) -> List[RedditResult]:
        """
        Search Reddit posts matching *query* across *subreddits*.

        Parameters
        ----------
        query:
            Search terms.
        subreddits:
            List of subreddit names (without r/). Defaults to SUBREDDITS.
        max_posts:
            Maximum posts to fetch per subreddit.
        max_age_days:
            Ignore posts older than this.

        Returns
        -------
        List[RedditResult]
        """
        target_subs = subreddits or SUBREDDITS
        all_results: List[RedditResult] = []

        for sub_name in target_subs:
            try:
                results = await asyncio.to_thread(
                    self._search_sub, sub_name, query, max_posts, max_age_days
                )
                all_results.extend(results)
            except Exception as exc:
                logger.warning("Reddit: failed to search r/%s: %s", sub_name, exc)

        logger.info(
            "Reddit: query=%r across %s → %d results",
            query, target_subs, len(all_results)
        )
        return all_results

    def _search_sub(
        self,
        sub_name: str,
        query: str,
        max_posts: int,
        max_age_days: int,
    ) -> List[RedditResult]:
        reddit = self._ensure()
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
        results: List[RedditResult] = []

        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.search(
                query, sort="relevance", time_filter="month", limit=max_posts
            ):
                if post.created_utc < cutoff:
                    continue
                results.append(RedditResult(
                    subreddit=sub_name,
                    title=post.title,
                    url=post.url,
                    author=str(post.author) if post.author else "[deleted]",
                    score=post.score,
                    num_comments=post.num_comments,
                    created_utc=post.created_utc,
                    selftext=post.selftext or "",
                    permalink=f"https://reddit.com{post.permalink}",
                ))
        except Exception as exc:
            logger.warning("Reddit: error searching r/%s: %s", sub_name, exc)

        return results


# ── Module-level singleton ────────────────────────────────────────────────────

_client: Optional[RedditClient] = None


async def search(
    query: str,
    subreddits: Optional[List[str]] = None,
    max_posts: int = MAX_POSTS_PER_SUB,
    max_age_days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper that returns plain dicts (not RedditResult objects).

    Returns
    -------
    List[dict]
    """
    global _client
    if _client is None:
        _client = RedditClient()

    results = await _client.search(
        query=query,
        subreddits=subreddits,
        max_posts=max_posts,
        max_age_days=max_age_days,
    )

    def _to_dict(r: Any) -> Dict[str, Any]:
        # Handle both RedditResult objects and plain dicts
        if isinstance(r, dict):
            return r
        return {
            "title": r.title,
            "url": r.url,
            "author": r.author,
            "score": r.score,
            "num_comments": r.num_comments,
            "created_utc": r.created_utc,
            "content": r.content_snippet,
            "permalink": r.permalink,
            "subreddit": r.subreddit,
            "platform": "reddit",
        }

    return [_to_dict(r) for r in results]


async def gather_searches(
    queries: List[str],
    subreddits: Optional[List[str]] = None,
    max_posts: int = MAX_POSTS_PER_SUB,
    max_age_days: int = 30,
) -> List[Dict[str, Any]]:
    """Run multiple Reddit searches concurrently."""
    if not queries:
        return []

    tasks = [
        search(query=q, subreddits=subreddits, max_posts=max_posts, max_age_days=max_age_days)
        for q in queries
    ]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: List[Dict[str, Any]] = []
    for i, res in enumerate(results_per_query):
        if isinstance(res, Exception):
            logger.error("Reddit: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)

    return all_results
