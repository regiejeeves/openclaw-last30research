"""
Tests for scripts/report.py
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts import report


class TestSentiment:
    def test_negative_keywords(self):
        result = {"title": "How to crack MQL5", "content": "bypass the license key"}
        assert report._sentiment(result) == "negative"

    def test_positive_keywords(self):
        result = {"title": "Great new release", "content": "love the fixed bugs"}
        assert report._sentiment(result) == "positive"

    def test_neutral(self):
        result = {"title": "MQL5 discussion", "content": "what is the typical setup used"}
        assert report._sentiment(result) == "neutral"


class TestQuote:
    def test_uses_content(self):
        result = {"content": "This is a long post content.", "selftext": ""}
        quote = report._quote(result)
        assert "This is a long post content" in quote

    def test_uses_selftext(self):
        result = {"content": "", "selftext": "I tried cracking but it failed."}
        quote = report._quote(result)
        assert "cracking" in quote, f"Expected 'cracking' in quote but got: {quote}"

    def test_empty_returns_dash(self):
        result = {"content": "", "selftext": ""}
        assert report._quote(result) == "—"

    def test_truncates_long_content(self):
        long_content = "x" * 300
        result = {"content": long_content, "selftext": ""}
        quote = report._quote(result)
        assert len(quote) <= 210  # 200 + '"' + '…'


class TestFindingFromResult:
    def test_id_is_consistent_for_same_title(self):
        r1 = {"title": "Same Title", "content": "content 1", "platform": "web", "url": "https://x.com"}
        r2 = {"title": "Same Title", "content": "content 2", "platform": "reddit", "url": "https://reddit.com"}
        f1 = report.Finding.from_result(r1)
        f2 = report.Finding.from_result(r2)
        assert f1.id == f2.id

    def test_id_differs_for_different_titles(self):
        r1 = {"title": "Title A", "content": "same", "platform": "web", "url": "https://x.com"}
        r2 = {"title": "Title B", "content": "same", "platform": "web", "url": "https://x.com"}
        f1 = report.Finding.from_result(r1)
        f2 = report.Finding.from_result(r2)
        assert f1.id != f2.id

    def test_platforms_list(self):
        r = {"title": "Test", "content": "...", "platform": "reddit", "url": "https://x.com"}
        f = report.Finding.from_result(r)
        assert f.platforms == ["reddit"]

    def test_default_values(self):
        r = {"title": "Test", "content": "...", "platform": "web", "url": "https://x.com"}
        f = report.Finding.from_result(r)
        assert f.is_new is True
        assert f.first_seen == ""


class TestBuildReport:
    def test_report_empty_results(self):
        r = report.build_report(
            topic="MQL5 cracking",
            project="lockingood",
            platforms=["reddit", "web"],
            days=30,
            all_results=[],
        )
        assert "MQL5 cracking" in r.generated_at or r.generated_at != ""
        assert len(r.findings) == 0

    def test_report_adds_findings(self):
        results = [
            {"title": "Post 1", "content": "content 1", "platform": "reddit", "url": "https://r.com"},
            {"title": "Post 2", "content": "content 2", "platform": "web", "url": "https://w.com"},
        ]
        r = report.build_report("test topic", "lockingood", ["reddit", "web"], 30, results)
        assert len(r.findings) == 2
        assert len(r.reddit_results) == 1
        assert len(r.web_results) == 1

    def test_report_deduplicates_against_previous(self):
        # Use the actual ID that from_result generates for "Post 1"
        import hashlib
        same_title_id = "finding-" + hashlib.md5(b"Post 1").hexdigest()[:8]
        prev_report = {
            "findings": [
                {"id": same_title_id, "title": "Post 1", "body": "content 1",
                 "sentiment": "neutral", "platforms": ["reddit"], "url": "https://r.com"},
            ],
            "date": "2026-03-15",
        }
        results = [
            {"title": "Post 1", "content": "content 1", "platform": "reddit", "url": "https://r.com"},
            {"title": "Post 2", "content": "content 2", "platform": "web", "url": "https://w.com"},
        ]
        r = report.build_report("test", "lockingood", ["reddit", "web"], 30,
                                  results, previous_report=prev_report)
        assert len(r.findings) == 2
        p1 = next(f for f in r.findings if "Post 1" in f.title)
        assert p1.is_new is False, f"Post 1 should be recurring (id={p1.id}, expected={same_title_id})"
        p2 = next(f for f in r.findings if "Post 2" in f.title)
        assert p2.is_new is True


class TestReportBuildMarkdown:
    def test_executive_summary_no_results(self):
        r = report.Report(topic="empty", project="lockingood", platforms=[], days=30)
        summary = r._executive_summary()
        assert "No results found" in summary

    def test_executive_summary_mentions_sentiment(self):
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        r.add_result({"title": "Bad crack", "content": "crack fail exploit", "platform": "web", "url": "https://x.com"})
        summary = r._executive_summary()
        assert "negative" in summary

    def test_sources_footer_counts(self):
        r = report.Report(topic="test", project="lockingood", platforms=["reddit", "web"], days=30)
        r.add_result({"title": "R1", "content": "...", "platform": "reddit", "url": "https://r.com", "author": "u", "score": 1, "num_comments": 0, "created_utc": 0, "permalink": ""})
        r.add_result({"title": "R2", "content": "...", "platform": "reddit", "url": "https://r.com", "author": "u", "score": 1, "num_comments": 0, "created_utc": 0, "permalink": ""})
        r.add_result({"title": "W1", "content": "...", "platform": "web", "url": "https://w.com", "score": 0.9, "published_date": None})
        footer = r._sources_footer()
        assert "Reddit 2" in footer
        assert "Web 1" in footer

    def test_sentiment_section(self):
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        r.add_result({"title": "neg", "content": "crack fail", "platform": "web", "url": "https://x.com"})
        r.add_result({"title": "neg", "content": "broken exploit", "platform": "web", "url": "https://x.com"})
        r.add_result({"title": "pos", "content": "great new fix", "platform": "web", "url": "https://x.com"})
        sentiment = r._sentiment_section()
        assert "Negative" in sentiment
        assert "Positive" in sentiment

    def test_full_build_runs_without_error(self):
        r = report.Report(topic="MQL5 cracking", project="lockingood",
                          platforms=["reddit", "web", "x"], days=30)
        r.add_result({"title": "Reddit post", "content": "someone cracking mt5",
                       "platform": "reddit", "url": "https://r.com",
                       "author": "u", "score": 5, "num_comments": 2, "created_utc": 0, "permalink": ""})
        r.add_result({"title": "Web article", "content": "license bypass tutorial",
                       "platform": "web", "url": "https://w.com",
                       "score": 0.9, "published_date": "2026-04-01"})
        markdown = r.build()
        assert "# Research: MQL5 cracking" in markdown
        assert "## Executive Summary" in markdown
        assert "## Key Findings" in markdown
        assert "## Platform Breakdown" in markdown
        assert "## Sentiment & Consensus" in markdown
        assert "## Recommendations" in markdown
        assert "*Sources:" in markdown
