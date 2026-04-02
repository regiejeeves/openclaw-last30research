"""
Telegram search via Telethon.

This searches the authenticated account's accessible dialogs and gathers recent
messages matching the query.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from telethon import TelegramClient
except ImportError:  # pragma: no cover - exercised through runtime guard
    TelegramClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_PATH = Path("/tmp/last30research-telegram")
MAX_DIALOGS = 10
MESSAGES_PER_DIALOG = 5


@dataclass
class TelegramResult:
    channel: str
    content: str
    url: str
    date: str
    sender_id: int = 0
    message_id: int = 0
    platform: str = "telegram"

    @property
    def content_snippet(self) -> str:
        return self.content[:500] + "…" if len(self.content) > 500 else self.content


def _message_text(message: Any) -> str:
    return str(
        getattr(message, "message", None)
        or getattr(message, "raw_text", None)
        or getattr(message, "text", None)
        or ""
    ).strip()


class TelegramSearcher:
    """Lazy Telethon wrapper."""

    def __init__(self) -> None:
        self._client: Any = None

    async def _ensure(self) -> Any:
        if TelegramClient is None:
            raise RuntimeError("telethon not installed — run: uv add telethon")
        if self._client is None:
            self._client = TelegramClient(str(SESSION_PATH), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        return self._client

    @staticmethod
    def _message_url(entity: Any, message_id: int) -> str:
        username = getattr(entity, "username", None)
        if username:
            return f"https://t.me/{username}/{message_id}"
        return ""

    async def search(
        self,
        query: str,
        days: int = 30,
        max_dialogs: int = MAX_DIALOGS,
        messages_per_dialog: int = MESSAGES_PER_DIALOG,
    ) -> List[TelegramResult]:
        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            logger.warning("Telegram: TELEGRAM_API_ID/TELEGRAM_API_HASH not set — skipping Telegram search.")
            return []

        try:
            client = await self._ensure()
        except Exception as exc:
            logger.warning("Telegram: %s", exc)
            return []

        if hasattr(client, "connect"):
            await client.connect()
        if hasattr(client, "is_user_authorized") and not await client.is_user_authorized():
            logger.warning("Telegram: session is not authorized — skipping Telegram search.")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results: List[TelegramResult] = []

        async for dialog in client.iter_dialogs(limit=max_dialogs):
            entity = getattr(dialog, "entity", dialog)
            channel_name = str(
                getattr(dialog, "name", None)
                or getattr(entity, "title", None)
                or getattr(entity, "username", None)
                or "unknown"
            )
            try:
                async for message in client.iter_messages(entity, search=query, limit=messages_per_dialog):
                    text = _message_text(message)
                    if not text:
                        continue
                    message_date = getattr(message, "date", None)
                    if isinstance(message_date, datetime):
                        if message_date.tzinfo is None:
                            message_date = message_date.replace(tzinfo=timezone.utc)
                        message_date = message_date.astimezone(timezone.utc)
                        if message_date < cutoff:
                            continue
                        message_date_str = message_date.isoformat()
                    else:
                        message_date_str = ""

                    results.append(
                        TelegramResult(
                            channel=channel_name,
                            content=text,
                            url=self._message_url(entity, int(getattr(message, "id", 0) or 0)),
                            date=message_date_str,
                            sender_id=int(getattr(message, "sender_id", 0) or 0),
                            message_id=int(getattr(message, "id", 0) or 0),
                        )
                    )
            except Exception as exc:
                logger.warning("Telegram: failed searching %s: %s", channel_name, exc)

        logger.info("Telegram: query=%r → %d results", query, len(results))
        return results


_client: Optional[TelegramSearcher] = None


async def search(
    query: str,
    days: int = 30,
    max_dialogs: int = MAX_DIALOGS,
    messages_per_dialog: int = MESSAGES_PER_DIALOG,
) -> List[Dict[str, Any]]:
    global _client
    if _client is None:
        _client = TelegramSearcher()

    results = await _client.search(
        query=query,
        days=days,
        max_dialogs=max_dialogs,
        messages_per_dialog=messages_per_dialog,
    )
    return [
        {
            "title": f"{result.channel}: {result.content_snippet[:80]}",
            "content": result.content_snippet,
            "channel": result.channel,
            "url": result.url,
            "date": result.date,
            "sender_id": result.sender_id,
            "message_id": result.message_id,
            "platform": "telegram",
        }
        for result in results
    ]


async def gather_searches(
    queries: List[str],
    days: int = 30,
    max_dialogs: int = MAX_DIALOGS,
    messages_per_dialog: int = MESSAGES_PER_DIALOG,
) -> List[Dict[str, Any]]:
    if not queries:
        return []

    tasks = [
        search(
            query=q,
            days=days,
            max_dialogs=max_dialogs,
            messages_per_dialog=messages_per_dialog,
        )
        for q in queries
    ]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: List[Dict[str, Any]] = []
    for i, res in enumerate(results_per_query):
        if isinstance(res, Exception):
            logger.error("Telegram: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)
    return all_results
