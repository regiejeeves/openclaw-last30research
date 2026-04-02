"""
Hacker News search via the public HN Algolia API.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - exercised through runtime guard
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

API_URL = "https://hn.algolia.com/api/v1/search_by_date"
MAX_RESULTS = 20


def _parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class HNResult:
    object_id: str
    title: str
    url: str
    author: str
    points: int
    num_comments: int
    created_at: str
    story_text: str = ""
    platform: str = "hn"

    @property
    def content_snippet(self) -> str:
        text = self.story_text or self.title
        return text[:500] + "…" if len(text) > 500 else text


class HNClient:
    """Lazy AsyncClient wrapper for HN Algolia."""

    def __init__(self) -> None:
        self._client: Optional["httpx.AsyncClient"] = None

    def _ensure(self) -> Optional["httpx.AsyncClient"]:
        if httpx is None:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    def _normalize_hit(self, hit: Dict[str, Any]) -> Optional[HNResult]:
        title = str(hit.get("title") or hit.get("story_title") or "").strip()
        object_id = str(hit.get("objectID") or "")
        if not title and not object_id:
            return None

        url = str(hit.get("url") or hit.get("story_url") or "")
        if not url and object_id:
            url = f"https://news.ycombinator.com/item?id={object_id}"

        story_text = str(hit.get("story_text") or hit.get("comment_text") or "")
        return HNResult(
            object_id=object_id,
            title=title or f"HN item {object_id}",
            url=url,
            author=str(hit.get("author") or "unknown"),
            points=int(hit.get("points") or 0),
            num_comments=int(hit.get("num_comments") or 0),
            created_at=str(hit.get("created_at") or ""),
            story_text=story_text,
        )

    async def search(
        self,
        query: str,
        days: int = 30,
        max_results: int = MAX_RESULTS,
        tags: str = "story",
    ) -> List[HNResult]:
        client = self._ensure()
        if client is None:
            logger.warning("HN: httpx not installed — run: uv add httpx")
            return []

        params = {
            "query": query,
            "tags": tags,
            "hitsPerPage": str(max_results),
        }
        response = await client.get(API_URL, params=params)
        response.raise_for_status()

        payload = response.json()
        hits = payload.get("hits", []) if isinstance(payload, dict) else []
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        results: List[HNResult] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            result = self._normalize_hit(hit)
            if result is None:
                continue
            created_at = _parse_datetime(result.created_at)
            if created_at and created_at < cutoff:
                continue
            results.append(result)

        logger.info("HN: query=%r → %d results", query, len(results))
        return results


_client: Optional[HNClient] = None


async def search(
    query: str,
    days: int = 30,
    max_results: int = MAX_RESULTS,
    tags: str = "story",
) -> List[Dict[str, Any]]:
    global _client
    if _client is None:
        _client = HNClient()

    results = await _client.search(query=query, days=days, max_results=max_results, tags=tags)
    return [
        {
            "title": result.title,
            "content": result.content_snippet,
            "url": result.url,
            "author": result.author,
            "score": result.points,
            "num_comments": result.num_comments,
            "created_at": result.created_at,
            "object_id": result.object_id,
            "platform": "hn",
        }
        for result in results
    ]


async def gather_searches(
    queries: List[str],
    days: int = 30,
    max_results: int = MAX_RESULTS,
    tags: str = "story",
) -> List[Dict[str, Any]]:
    if not queries:
        return []

    tasks = [
        search(query=q, days=days, max_results=max_results, tags=tags)
        for q in queries
    ]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: List[Dict[str, Any]] = []
    for i, res in enumerate(results_per_query):
        if isinstance(res, Exception):
            logger.error("HN: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)
    return all_results
