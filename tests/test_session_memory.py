"""
Tests for scripts/session_memory.py
"""
import json
import pytest
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestSaveLoad:
    def test_save_and_load_roundtrip(self, monkeypatch, tmp_path):
        """A saved report can be loaded back."""
        monkeypatch.setattr("scripts.session_memory.MEMORY_DIR", tmp_path)

        from scripts import session_memory

        findings = [
            {"id": "finding-abc", "title": "Test finding", "body": "body text",
             "sentiment": "neutral", "platforms": ["reddit"], "is_new": True,
             "url": "https://x.com"}
        ]

        path = session_memory.save_report(
            project="lockingood",
            topic="MQL5 cracking",
            platforms=["reddit", "web"],
            days=30,
            findings=findings,
            report_path="/obsidian/vault/research/mql5-2026-04-02.md",
        )

        assert path.exists()

        loaded = session_memory.load_last_report("lockingood")
        assert loaded is not None
        assert loaded["project"] == "lockingood"
        assert loaded["topic"] == "MQL5 cracking"
        assert len(loaded["findings"]) == 1
        assert loaded["findings"][0]["id"] == "finding-abc"

    def test_load_last_report_no_file(self, monkeypatch, tmp_path):
        """Returns None when no previous report exists."""
        monkeypatch.setattr("scripts.session_memory.MEMORY_DIR", tmp_path)
        from scripts import session_memory
        result = session_memory.load_last_report("nonexistent-project")
        assert result is None

    def test_save_report_handles_errors_gracefully(self, monkeypatch, tmp_path):
        """save_report does not crash when path.write_text raises an OSError."""
        good_memory_dir = tmp_path / "memory"
        good_memory_dir.mkdir()
        monkeypatch.setattr("scripts.session_memory.MEMORY_DIR", good_memory_dir)

        # Make the file path read-only so write_text fails
        readonly_file = good_memory_dir / "lockingood-2026-04-02.json"
        readonly_file.write_text("{}")  # create it first
        readonly_file.chmod(0o444)  # read-only

        from scripts import session_memory
        # Should not raise — errors are caught and logged
        path = session_memory.save_report(
            project="lockingood", topic="t", platforms=[], days=30,
            findings=[], report_path=""
        )
        # No exception should have been raised

    def test_list_recent_reports(self, monkeypatch, tmp_path):
        """Returns up to N recent reports."""
        monkeypatch.setattr("scripts.session_memory.MEMORY_DIR", tmp_path)
        from scripts import session_memory

        for i in range(5):
            data = {"project": "lockingood", "topic": f"Topic {i}",
                    "date": f"2026-04-{i:02d}", "findings": [], "platforms": [], "days": 30, "report_path": ""}
            (tmp_path / f"lockingood-2026-04-{i:02d}.json").write_text(json.dumps(data))

        reports = session_memory.list_recent_reports("lockingood", limit=3)
        assert len(reports) == 3
        # Most recent first
        assert reports[0]["topic"] == "Topic 4"

    def test_list_recent_reports_empty_dir(self, monkeypatch, tmp_path):
        """Returns empty list for empty directory."""
        monkeypatch.setattr("scripts.session_memory.MEMORY_DIR", tmp_path)
        from scripts import session_memory
        reports = session_memory.list_recent_reports("lockingood")
        assert reports == []
