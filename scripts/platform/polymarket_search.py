"""
Polymarket public market search via the Gamma markets API.
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

API_URL = "https://gamma-api.polymarket.com/markets"
MAX_RESULTS = 20


def _parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matches_query(query: str, market: Dict[str, Any]) -> int:
    haystack = " ".join(
        str(market.get(key) or "")
        for key in ("question", "title", "description", "category", "slug")
    ).lower()
    tokens = [token for token in query.lower().split() if len(token) > 2]
    if not tokens:
        return 1
    return sum(token in haystack for token in tokens)


@dataclass
class PolymarketResult:
    market_id: str
    question: str
    url: str
    description: str
    category: str
    volume: str
    liquidity: str
    end_date: str
    platform: str = "polymarket"

    @property
    def content_snippet(self) -> str:
        text = self.description or self.question
        return text[:500] + "…" if len(text) > 500 else text


class PolymarketClient:
    """Lazy AsyncClient wrapper for Polymarket."""

    def __init__(self) -> None:
        self._client: Optional["httpx.AsyncClient"] = None

    def _ensure(self) -> Optional["httpx.AsyncClient"]:
        if httpx is None:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    def _normalize_market(self, market: Dict[str, Any]) -> Optional[PolymarketResult]:
        question = str(market.get("question") or market.get("title") or "").strip()
        if not question:
            return None

        slug = str(market.get("slug") or "")
        url = str(market.get("url") or "")
        if not url and slug:
            url = f"https://polymarket.com/event/{slug}"

        return PolymarketResult(
            market_id=str(market.get("id") or ""),
            question=question,
            url=url,
            description=str(market.get("description") or ""),
            category=str(market.get("category") or ""),
            volume=str(market.get("volume") or "0"),
            liquidity=str(market.get("liquidity") or "0"),
            end_date=str(market.get("endDate") or ""),
        )

    async def search(
        self,
        query: str,
        days: int = 30,
        max_results: int = MAX_RESULTS,
    ) -> List[PolymarketResult]:
        client = self._ensure()
        if client is None:
            logger.warning("Polymarket: httpx not installed — run: uv add httpx")
            return []

        response = await client.get(
            API_URL,
            params={
                "limit": str(max_results * 4),
                "active": "true",
                "closed": "false",
            },
        )
        response.raise_for_status()
        payload = response.json()
        markets = payload if isinstance(payload, list) else []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        scored: List[tuple[int, float, PolymarketResult]] = []
        for market in markets:
            if not isinstance(market, dict):
                continue
            match_score = _matches_query(query, market)
            if match_score <= 0:
                continue

            updated_at = _parse_datetime(
                str(market.get("updatedAt") or market.get("createdAt") or "")
            )
            if updated_at and updated_at < cutoff:
                continue

            result = self._normalize_market(market)
            if result is None:
                continue

            try:
                volume = float(market.get("volume") or 0)
            except (TypeError, ValueError):
                volume = 0.0
            scored.append((match_score, volume, result))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        results = [result for _, _, result in scored[:max_results]]
        logger.info("Polymarket: query=%r → %d results", query, len(results))
        return results


_client: Optional[PolymarketClient] = None


async def search(
    query: str,
    days: int = 30,
    max_results: int = MAX_RESULTS,
) -> List[Dict[str, Any]]:
    global _client
    if _client is None:
        _client = PolymarketClient()

    results = await _client.search(query=query, days=days, max_results=max_results)
    return [
        {
            "title": result.question,
            "question": result.question,
            "content": result.content_snippet,
            "url": result.url,
            "market_id": result.market_id,
            "volume": result.volume,
            "liquidity": result.liquidity,
            "category": result.category,
            "end_date": result.end_date,
            "platform": "polymarket",
        }
        for result in results
    ]


async def gather_searches(
    queries: List[str],
    days: int = 30,
    max_results: int = MAX_RESULTS,
) -> List[Dict[str, Any]]:
    if not queries:
        return []

    tasks = [search(query=q, days=days, max_results=max_results) for q in queries]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: List[Dict[str, Any]] = []
    for i, res in enumerate(results_per_query):
        if isinstance(res, Exception):
            logger.error("Polymarket: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)
    return all_results
