"""
YouTube discovery via yt-dlp plus Gemini-based audio transcription.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised through runtime guard
    genai = None  # type: ignore[assignment]

try:
    from yt_dlp import YoutubeDL
except ImportError:  # pragma: no cover - exercised through runtime guard
    YoutubeDL = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MAX_RESULTS = 3
GEMINI_MODEL = "gemini-2.5-flash"


def _parse_upload_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


@dataclass
class YouTubeResult:
    video_id: str
    title: str
    url: str
    channel: str
    published_at: str
    transcript: str
    description: str = ""
    view_count: int = 0
    platform: str = "youtube"

    @property
    def content_snippet(self) -> str:
        text = self.transcript or self.description or self.title
        return text[:500] + "…" if len(text) > 500 else text


class YouTubeClient:
    """Lazy yt-dlp + Gemini wrapper."""

    def __init__(self, model: str = GEMINI_MODEL) -> None:
        self._genai_client: Any = None
        self.model = model

    def _ensure_genai(self) -> Any:
        if genai is None:
            raise RuntimeError("google-genai not installed — run: uv add google-genai")
        if self._genai_client is None:
            self._genai_client = genai.Client(api_key=GEMINI_API_KEY)
        return self._genai_client

    def _search_videos_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        if YoutubeDL is None:
            raise RuntimeError("yt-dlp not installed — run: uv add yt-dlp")

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
        }
        with YoutubeDL(options) as ydl:
            payload = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False) or {}
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        return [entry for entry in entries if isinstance(entry, dict)]

    def _download_audio_sync(self, url: str, temp_dir: str) -> str:
        if YoutubeDL is None:
            raise RuntimeError("yt-dlp not installed — run: uv add yt-dlp")

        output_template = str(Path(temp_dir) / "%(id)s.%(ext)s")
        options = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "noplaylist": True,
            "outtmpl": output_template,
        }
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True) or {}
            requested_downloads = info.get("requested_downloads") or []
            if requested_downloads:
                filepath = requested_downloads[0].get("filepath")
                if filepath:
                    return filepath
            return ydl.prepare_filename(info)

    def _transcribe_audio_sync(self, audio_path: str) -> str:
        client = self._ensure_genai()
        uploaded = client.files.upload(file=audio_path)
        response = client.models.generate_content(
            model=self.model,
            contents=[
                "Transcribe this YouTube audio and summarize the useful research signals in plain text.",
                uploaded,
            ],
        )
        return getattr(response, "text", "") or ""

    async def search(
        self,
        query: str,
        days: int = 30,
        max_results: int = MAX_RESULTS,
    ) -> List[YouTubeResult]:
        if not GEMINI_API_KEY:
            logger.warning("YouTube: GEMINI_API_KEY not set — skipping YouTube search.")
            return []
        if YoutubeDL is None:
            logger.warning("YouTube: yt-dlp not installed — run: uv add yt-dlp")
            return []
        if genai is None:
            logger.warning("YouTube: google-genai not installed — run: uv add google-genai")
            return []

        entries = await asyncio.to_thread(self._search_videos_sync, query, max_results)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        results: List[YouTubeResult] = []
        for entry in entries:
            published_dt = _parse_upload_date(str(entry.get("upload_date") or ""))
            if published_dt and published_dt < cutoff:
                continue

            video_id = str(entry.get("id") or "")
            url = str(entry.get("webpage_url") or entry.get("url") or "")
            if not url and video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"

            transcript = ""
            try:
                with tempfile.TemporaryDirectory(prefix="last30research-yt-") as temp_dir:
                    audio_path = await asyncio.to_thread(self._download_audio_sync, url, temp_dir)
                    transcript = await asyncio.to_thread(self._transcribe_audio_sync, audio_path)
            except Exception as exc:
                logger.warning("YouTube: transcription failed for %s: %s", url or video_id, exc)

            results.append(
                YouTubeResult(
                    video_id=video_id,
                    title=str(entry.get("title") or "Untitled"),
                    url=url,
                    channel=str(entry.get("channel") or entry.get("uploader") or "unknown"),
                    published_at=published_dt.isoformat() if published_dt else "",
                    transcript=transcript,
                    description=str(entry.get("description") or ""),
                    view_count=int(entry.get("view_count") or 0),
                )
            )

        logger.info("YouTube: query=%r → %d results", query, len(results))
        return results


_client: Optional[YouTubeClient] = None


async def search(
    query: str,
    days: int = 30,
    max_results: int = MAX_RESULTS,
) -> List[Dict[str, Any]]:
    global _client
    if _client is None:
        _client = YouTubeClient()

    results = await _client.search(query=query, days=days, max_results=max_results)
    return [
        {
            "title": result.title,
            "content": result.content_snippet,
            "transcript": result.transcript,
            "description": result.description,
            "url": result.url,
            "channel": result.channel,
            "published_at": result.published_at,
            "view_count": result.view_count,
            "video_id": result.video_id,
            "platform": "youtube",
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
            logger.error("YouTube: query %d raised %r — skipping", i, res)
            continue
        all_results.extend(res)
    return all_results
