"""
X / Twitter search via the bird CLI.

bird is a Node CLI (`@steipete/bird`), so this wrapper shells out to the
installed binary and normalizes JSON output into the common platform shape.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
CT0 = os.environ.get("CT0", "")
MAX_RESULTS = 10


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


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("tweets", "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested
    return []


def _first_value(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data.get(key)
    return None


@dataclass
class XResult:
    tweet_id: str
    username: str
    text: str
    url: str
    created_at: str
    display_name: str = ""
    like_count: int = 0
    reply_count: int = 0
    retweet_count: int = 0
    quote_count: int = 0
    platform: str = "x"

    @property
    def content_snippet(self) -> str:
        text = self.text.strip()
        return text[:500] + "…" if len(text) > 500 else text


class BirdClient:
    """Lazy bird CLI wrapper."""

    def __init__(self) -> None:
        self._command: Optional[List[str]] = None

    def _ensure_command(self) -> Optional[List[str]]:
        if self._command is not None:
            return self._command

        if shutil.which("bird"):
            self._command = ["bird"]
        elif shutil.which("npx"):
            self._command = ["npx", "-y", "@steipete/bird"]
        elif shutil.which("bunx"):
            self._command = ["bunx", "@steipete/bird"]
        else:
            self._command = None

        return self._command

    def _normalize_tweet(self, item: Dict[str, Any]) -> Optional[XResult]:
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        legacy = item.get("legacy") if isinstance(item.get("legacy"), dict) else {}

        tweet_id = str(_first_value(item, "id_str", "rest_id", "id", "tweet_id") or "")
        username = str(
            _first_value(
                item,
                "username",
                "screen_name",
                "userName",
                "handle",
            )
            or _first_value(author, "screen_name", "username", "userName", "handle")
            or ""
        ).lstrip("@")

        text = str(
            _first_value(
                item,
                "full_text",
                "text",
                "rawContent",
                "content",
            )
            or _first_value(legacy, "full_text", "text")
            or ""
        ).strip()
        created_at_raw = str(
            _first_value(item, "created_at", "createdAt") or _first_value(legacy, "created_at") or ""
        )
        if not text:
            return None

        url = str(item.get("url") or "")
        if not url and tweet_id and username:
            url = f"https://x.com/{username}/status/{tweet_id}"

        return XResult(
            tweet_id=tweet_id,
            username=username or "unknown",
            display_name=str(
                _first_value(item, "name", "display_name") or _first_value(author, "name", "display_name") or ""
            ),
            text=text,
            url=url,
            created_at=created_at_raw,
            like_count=int(_first_value(item, "favorite_count", "like_count", "likes") or 0),
            reply_count=int(_first_value(item, "reply_count", "replies") or 0),
            retweet_count=int(_first_value(item, "retweet_count", "retweets") or 0),
            quote_count=int(_first_value(item, "quote_count", "quotes") or 0),
        )

    async def search(
        self,
        query: str,
        days: int = 30,
        max_results: int = MAX_RESULTS,
        max_pages: int = 1,
    ) -> List[XResult]:
        if not AUTH_TOKEN or not CT0:
            logger.warning("X: CT0/AUTH_TOKEN not set — skipping X search.")
            return []

        command = self._ensure_command()
        if not command:
            logger.warning("X: bird CLI not found — install `@steipete/bird`.")
            return []

        proc = await asyncio.create_subprocess_exec(
            *command,
            "search",
            query,
            "-n",
            str(max_results),
            "--max-pages",
            str(max_pages),
            "--json",
            "--plain",
            "--auth-token",
            AUTH_TOKEN,
            "--ct0",
            CT0,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(
                "X: bird search failed for query=%r: %s",
                query,
                stderr.decode("utf-8", errors="replace").strip() or f"exit {proc.returncode}",
            )
            return []

        try:
            payload = json.loads(stdout.decode("utf-8") or "[]")
        except json.JSONDecodeError as exc:
            logger.warning("X: failed to parse bird JSON output: %s", exc)
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results: List[XResult] = []
        for item in _extract_items(payload):
            result = self._normalize_tweet(item)
            if result is None:
                continue

            created_at = _parse_datetime(result.created_at)
            if created_at and created_at < cutoff:
                continue
            results.append(result)

        logger.info("X: query=%r → %d results", query, len(results))
        return results


_client: Optional[BirdClient] = None


async def search(
    query: str,
    days: int = 30,
    max_results: int = MAX_RESULTS,
    max_pages: int = 1,
) -> List[Dict[str, Any]]:
    global _client
    if _client is None:
        _client = BirdClient()

    results = await _client.search(
        query=query,
        days=days,
        max_results=max_results,
        max_pages=max_pages,
    )
    return [
        {
            "title": f"@{result.username}: {result.content_snippet[:80]}",
            "content": result.content_snippet,
            "text": result.text,
            "url": result.url,
            "username": result.username,
            "display_name": result.display_name,
            "created_at": result.created_at,
            "tweet_id": result.tweet_id,
            "like_count": result.like_count,
            "reply_count": result.reply_count,
            "retweet_count": result.retweet_count,
            "quote_count": result.quote_count,
            "platform": "x",
        }
        for result in results
    ]


async def gather_searches(
    queries: List[str],
    days: int = 30,
    max_results: int = MAX_RESULTS,
    max_pages: int = 1,
) -> List[Dict[str, Any]]:
    if not queries:
        return []

    tasks = [
        search(query=q, days=days, max_results=max_results, max_pages=max_pages)
        for q in queries
    ]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: List[Dict[str, Any]] = []
    for i, res in enumerate(results_per_query):
        if isinstance(res, Exception):
            logger.error("X: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)
    return all_results
