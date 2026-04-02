#!/usr/bin/env python3
"""
last30research — main orchestrator.

Async parallel research across Reddit, X, Web (Tavily), HN, YouTube, Telegram,
Polymarket → structured intelligence report.

Usage:
    python -m scripts.research --topic "MQL5 license cracking" --project lockingood
    python -m scripts.research --topic "forex ea" --platforms reddit,x --days 7
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add scripts/ to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from scripts import report, session_memory
from scripts.platform import (
    hn_search,
    polymarket_search,
    reddit_search,
    tavily_search,
    telegram_search,
    x_search,
    youtube_search,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("last30research")


# ── Platform stubs (Phase 2 = wrappers wired behind same helpers) ────────────

async def _search_x(query: str, days: int) -> List[Dict[str, Any]]:
    """X / Twitter wrapper."""
    return await x_search.search(query=query, days=days)


async def _search_hn(query: str, days: int) -> List[Dict[str, Any]]:
    """Hacker News wrapper."""
    return await hn_search.search(query=query, days=days)


async def _search_youtube(query: str, days: int) -> List[Dict[str, Any]]:
    """YouTube wrapper."""
    return await youtube_search.search(query=query, days=days)


async def _search_telegram(query: str, days: int) -> List[Dict[str, Any]]:
    """Telegram wrapper."""
    return await telegram_search.search(query=query, days=days)


async def _search_polymarket(query: str, days: int) -> List[Dict[str, Any]]:
    """Polymarket wrapper."""
    return await polymarket_search.search(query=query, days=days)


# ── Platform dispatcher ─────────────────────────────────────────────────────────

PLATFORM_ENABLED: Dict[str, bool] = {
    "reddit": True,
    "x": True,
    "web": True,
    "hn": True,
    "youtube": True,
    "telegram": True,
    "polymarket": True,
}


def _enrich_query(query: str, keywords: List[str]) -> str:
    """Append domain keywords to a query for better relevance."""
    if keywords:
        kw_str = " OR ".join(keywords[:5])
        return f"({query}) AND ({kw_str})"
    return query


async def _run_platform_searches(
    query: str,
    platforms: List[str],
    keywords: List[str],
    days: int,
    depth: str,
) -> List[Dict[str, Any]]:
    """
    Fire all enabled platform searches in parallel and return flat results.
    """
    enriched = _enrich_query(query, keywords)
    tasks: List[Tuple[str, asyncio.Task]] = []

    for platform in platforms:
        platform_lower = platform.lower()
        if platform_lower == "reddit":
            tasks.append(("reddit", asyncio.create_task(
                reddit_search.gather_searches(
                    queries=[query, enriched],
                    max_age_days=days,
                )
            )))
        elif platform_lower == "web":
            tasks.append(("web", asyncio.create_task(
                tavily_search.gather_searches(
                    queries=[query, enriched],
                    days=days,
                    depth=depth,
                    max_results=10,
                )
            )))
        elif platform_lower == "x":
            tasks.append(("x", asyncio.create_task(_search_x(enriched, days))))
        elif platform_lower == "hn":
            tasks.append(("hn", asyncio.create_task(_search_hn(enriched, days))))
        elif platform_lower == "youtube":
            tasks.append(("youtube", asyncio.create_task(_search_youtube(enriched, days))))
        elif platform_lower == "telegram":
            tasks.append(("telegram", asyncio.create_task(_search_telegram(enriched, days))))
        elif platform_lower == "polymarket":
            tasks.append(("polymarket", asyncio.create_task(_search_polymarket(enriched, days))))

    results: List[Dict[str, Any]] = []
    for name, task in tasks:
        try:
            platform_results = await task
            for r in platform_results:
                r.setdefault("platform", name)
            results.extend(platform_results)
            logger.info("%s: %d results", name, len(platform_results))
        except Exception as exc:
            logger.error("%s: search failed with %r", name, exc)

    return results


# ── Config loading ─────────────────────────────────────────────────────────────

def load_project_config(project_name: str | None) -> dict:
    """Load project config from projects.yaml, falling back to defaults."""
    import yaml

    config_path = Path(__file__).parent.parent / "config" / "projects.yaml"
    if not config_path.exists():
        logger.warning("projects.yaml not found at %s — using defaults", config_path)
        return {
            "default_platforms": ["reddit", "x", "web"],
            "domain_keywords": [],
            "priority": "general",
            "vault_path": None,
        }

    try:
        with open(config_path) as f:
            full_config = yaml.safe_load(f)
    except Exception as exc:
        logger.warning("Failed to parse projects.yaml: %s — using defaults", exc)
        return {
            "default_platforms": ["reddit", "x", "web"],
            "domain_keywords": [],
            "priority": "general",
            "vault_path": None,
        }

    projects = full_config.get("projects", {})
    global_defaults = {
        k: v for k, v in full_config.items()
        if k not in ("projects",)
    }

    project_config = projects.get(project_name or "lockingood", {})
    # Merge global defaults under project
    merged = {**global_defaults, **project_config}
    merged["default_platforms"] = project_config.get(
        "default_platforms",
        global_defaults.get("default_platforms", ["reddit", "x", "web"]),
    )
    return merged


# ── Obsidian save ──────────────────────────────────────────────────────────────

def _slugify(value: str, max_length: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:max_length] or "research"


def _topic_tag(topic: str) -> str:
    return _slugify(topic, max_length=40)


def _build_obsidian_frontmatter(topic: str, project: str, platforms: List[str]) -> str:
    date_iso = datetime.now(timezone.utc).date().isoformat()
    topic_tag = _topic_tag(topic)
    lines = [
        "---",
        f"date: {date_iso}",
        "tags:",
        "- research",
        f"- {topic_tag}",
        "type: research-report",
        "source: last30research",
        "platforms:",
    ]
    lines.extend(f"- {platform}" for platform in platforms)
    lines.append(f"project: {project}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


async def save_to_obsidian(
    content: str,
    vault_path: str | None,
    topic: str,
    folder: str,
    platforms: List[str],
    project: str,
) -> Path | None:
    """Save the report markdown to an Obsidian vault."""
    if not vault_path:
        logger.info("Obsidian: no vault_path configured — skipping save")
        return None

    vault_expanded = os.path.expanduser(vault_path)
    vault = Path(vault_expanded)
    if not vault.exists():
        logger.warning("Obsidian vault does not exist at %s — skipping save", vault_expanded)
        return None

    slug = _slugify(topic)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{slug}-{date_str}.md"
    dest = vault / folder / filename

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = _build_obsidian_frontmatter(topic, project, platforms)
        dest.write_text(frontmatter + content)
        logger.info("Saved to Obsidian: %s", dest)
        return dest
    except Exception as exc:
        logger.warning("Failed to save to Obsidian: %s", exc)
        return None


def deliver_report_to_chat(markdown: str, topic: str, project: str, platforms: List[str]) -> str:
    """Emit a completion notification and return the chat-deliverable report."""
    logger.info(
        "Chat notification: research complete for topic=%r project=%r platforms=%s",
        topic,
        project,
        ",".join(platforms),
    )
    return markdown


# ── Main research run ──────────────────────────────────────────────────────────

async def run_research(
    topic: str,
    project: str = "lockingood",
    platforms: Optional[List[str]] = None,
    days: int = 30,
    save: bool = True,
    folder: str = "research",
    deepen: str | None = None,
    depth: str = "basic",
    deep: bool = False,
) -> str:
    """
    Execute a full research run and return the report as a markdown string.

    Parameters
    ----------
    topic:
        Research query.
    project:
        Project name (from projects.yaml).
    platforms:
        List of platforms to search. None = project default.
    days:
        Time window.
    save:
        Whether to save the report to Obsidian.
    folder:
        Obsidian subfolder for saved reports.
    deepen:
        Finding ID to drill into (loads previous report for context).
    depth:
        Tavily search depth.

    Returns
    -------
    str
        The complete report in markdown format.
    """
    config = load_project_config(project)
    all_platforms = ["reddit", "x", "web", "hn", "youtube", "telegram", "polymarket"]
    if deep:
        enabled_platforms = all_platforms
        depth = "advanced"
    else:
        enabled_platforms = platforms or config.get("default_platforms", ["reddit", "x", "web"])
    keywords = config.get("domain_keywords", [])
    vault_path = config.get("vault_path")
    priority = config.get("priority", "general")

    logger.info(
        "Research starting: topic=%r project=%r platforms=%r days=%d",
        topic, project, enabled_platforms, days,
    )

    # Load previous report for deduplication / deepen context
    previous = session_memory.load_last_report(project) if not deepen else None

    if deepen and previous:
        logger.info("--deepen=%s: loaded previous report from %s", deepen, previous.get("date"))

    # Run all platform searches in parallel
    all_results = await _run_platform_searches(
        query=topic,
        platforms=enabled_platforms,
        keywords=keywords,
        days=days,
        depth=depth,
    )

    logger.info("Total results collected: %d", len(all_results))

    # Build structured report
    report_obj = report.build_report(
        topic=topic,
        project=project,
        platforms=enabled_platforms,
        days=days,
        all_results=all_results,
        previous_report=previous,
    )
    markdown = report_obj.build()

    # Save to Obsidian
    saved_path: Path | None = None
    if save:
        saved_path = await save_to_obsidian(
            markdown,
            vault_path,
            topic,
            folder,
            enabled_platforms,
            project,
        )

    # Save session memory for --deepen follow-up
    findings_data = [
        {"id": f.id, "title": f.title, "body": f.body, "sentiment": f.sentiment,
         "platforms": f.platforms, "is_new": f.is_new, "url": f.proof_url}
        for f in report_obj.findings
    ]
    report_path = str(saved_path) if saved_path else ""
    session_memory.save_report(
        project=project,
        topic=topic,
        platforms=enabled_platforms,
        days=days,
        findings=findings_data,
        report_path=report_path,
    )

    return deliver_report_to_chat(markdown, topic, project, enabled_platforms)


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="last30research — multi-platform deep research")
    parser.add_argument("--topic", "-t", required=True, help="Research topic / query")
    parser.add_argument("--project", "-p", default="lockingood", help="Project name")
    parser.add_argument(
        "--platforms", "-P", nargs="+",
        help="Platforms: reddit x web hn youtube telegram polymarket"
    )
    parser.add_argument("--days", "-d", type=int, default=30, help="Time window (7/14/30/90)")
    parser.add_argument("--no-save", action="store_true", help="Skip Obsidian save")
    parser.add_argument("--folder", "-f", default="research", help="Obsidian subfolder")
    parser.add_argument("--deepen", help="Finding ID to drill into from previous report")
    parser.add_argument("--depth", default="basic", help="Tavily depth: ultra-fast/fast/basic/advanced")
    parser.add_argument("--deep", action="store_true", help="Full mode: all platforms + advanced depth (~5min)")
    parser.add_argument("--quick", action="store_true", help="Fast mode: reddit,x,web only")
    parser.add_argument("--all", action="store_true", help="All platforms")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()

    if args.quick:
        platforms = ["reddit", "x", "web"]
    elif args.all:
        platforms = ["reddit", "x", "web", "hn", "youtube", "telegram", "polymarket"]
    elif args.platforms:
        platforms = args.platforms
    else:
        platforms = None  # use project default



    result = await run_research(
        topic=args.topic,
        project=args.project,
        platforms=platforms,
        days=args.days,
        save=not args.no_save,
        folder=args.folder,
        deepen=args.deepen,
        depth=args.depth,
        deep=args.deep,
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
