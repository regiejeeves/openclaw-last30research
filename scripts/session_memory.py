"""
Session memory for last30research.
Stores the last report per project for follow-up via --deepen.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MEMORY_DIR = Path("~/.openclaw/workspace/memory/last30research").expanduser()


def _ensure_memory_dir() -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return MEMORY_DIR


def _memory_path(project: str) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _ensure_memory_dir() / f"{project}-{today}.json"


def save_report(
    project: str,
    topic: str,
    platforms: list[str],
    days: int,
    findings: list[dict[str, Any]],
    report_path: str,
) -> Path:
    """
    Save the last research run to a memory file for --deepen follow-up.

    Returns the path where the report was saved.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = _memory_path(project)
    data = {
        "project": project,
        "topic": topic,
        "date": today,
        "platforms": platforms,
        "days": days,
        "findings": findings,
        "report_path": report_path,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("Session memory saved: %s", path)
    except Exception as exc:
        logger.warning("Failed to save session memory to %s: %s", path, exc)
    return path


def load_last_report(project: str) -> Optional[dict[str, Any]]:
    """
    Load the most recent memory file for *project*.

    Returns None if no previous report exists.
    """
    memory_dir = _ensure_memory_dir()
    if not memory_dir.exists():
        return None

    # Find most recent file for this project
    project_files = sorted(
        memory_dir.glob(f"{project}-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not project_files:
        return None

    try:
        data = json.loads(project_files[0].read_text())
        logger.info("Loaded previous report from: %s", project_files[0])
        return data
    except Exception as exc:
        logger.warning("Failed to load previous report %s: %s", project_files[0], exc)
        return None


def list_recent_reports(project: str, limit: int = 5) -> list[dict[str, Any]]:
    """List the most recent N reports for a project."""
    memory_dir = _ensure_memory_dir()
    if not memory_dir.exists():
        return []

    files = sorted(
        memory_dir.glob(f"{project}-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    reports = []
    for f in files:
        try:
            reports.append(json.loads(f.read_text()))
        except Exception:
            pass
    return reports
