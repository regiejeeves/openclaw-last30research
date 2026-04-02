"""
Tavily Search API wrapper for last30research.
Provides async web search via the Tavily API.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_API_KEY = os.environ.get("TAVILY_API_KEY", "")
_TIMEOUT = 30.0  # seconds per request


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_to_timerange(days: int) -> str:
    """Map approximate day count to Tavily time_range string."""
    if days <= 1:
        return "day"
    elif days <= 7:
        return "week"
    elif days <= 30:
        return "month"
    else:
        return "year"


def _depth_to_search_depth(depth: str) -> str:
    """Normalise depth string to Tavily search_depth values."""
    mapping = {
        "ultra-fast": "ultra-fast",
        "fast": "fast",
        "basic": "basic",
        "advanced": "advanced",
    }
    return mapping.get(depth, "basic")


# ── Core search ───────────────────────────────────────────────────────────────

async def search(
    query: str,
    days: int = 30,
    depth: str = "basic",
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Run a web search via the Tavily API and return structured results.

    Parameters
    ----------
    query:
        Raw search query string.
    days:
        Time window in days (1, 7, 30, 90 → day/week/month/year).
    depth:
        Search depth: "ultra-fast", "fast", "basic", "advanced".
    max_results:
        Maximum number of results to return (1-20 for Tavily).

    Returns
    -------
    list[dict]
        Each dict contains: ``title``, ``url``, ``content``, ``score``,
        ``published_date`` (may be None).
    """
    if not _API_KEY:
        logger.warning("Tavily: TAVILY_API_KEY not set — skipping web search.")
        return []

    if TavilyClient is None:
        logger.error("Tavily: tavily package not installed — run: uv add tavily")
        return []

    for attempt in range(4):  # 3 retries
        try:
            api = TavilyClient(api_key=_API_KEY)

            search_depth = _depth_to_search_depth(depth)
            time_range = _days_to_timerange(days)

            raw = api.search(
                query=query,
                search_depth=search_depth,
                time_range=time_range,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,
                include_images=False,
            )

            # Quality filter: only keep results that mention specific MQL5/license keywords
            # in the title (Tavily score is already a relevance signal; this is a quality gate)
            _QUALITY_KW = [
                "license", "crack", "protect", "key ", "activation",
                "ex5", "ex4", "mql5", "mql4",
            ]

            def _is_quality(item: dict) -> bool:
                title = item.get("title", "").lower()
                # Title must have at least one quality keyword
                return any(kw in title for kw in _QUALITY_KW)

            raw_results = raw.get("results", [])
            quality = [r for r in raw_results if _is_quality(r)]

            results: list[dict[str, Any]] = []
            for item in (quality or raw_results)[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0.0),
                    "published_date": item.get("published_date"),
                    "platform": "web",
                })

            logger.info(
                "Tavily: query=%r → %d results (depth=%s)",
                query, len(results), search_depth,
            )
            return results

        except Exception as exc:
            logger.warning("Tavily: unexpected error on attempt %d: %s", attempt + 1, exc)

        if attempt < 3:
            wait = 2.0 ** (attempt + 1)
            logger.info("Tavily: retrying in %.1fs …", wait)
            await asyncio.sleep(wait)

    logger.error("Tavily: all retries exhausted for query=%r — returning empty list", query)
    return []


async def gather_searches(
    queries: list[str],
    days: int = 30,
    depth: str = "basic",
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Run multiple Tavily searches concurrently.

    Parameters
    ----------
    queries:
        List of query strings to search in parallel.
    days, depth, max_results:
        Passed through to :func:`search`.

    Returns
    -------
    list[dict]
        Flattened list of all results from all queries.
    """
    if not queries:
        return []

    tasks = [
        search(query=q, days=days, depth=depth, max_results=max_results)
        for q in queries
    ]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: list[dict[str, Any]] = []
    for i, res in enumerate(results_per_query):
        if isinstance(res, Exception):
            logger.error("Tavily: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)

    return all_results
