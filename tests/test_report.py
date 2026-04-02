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


class TestFollowUpCandidates:
    def test_empty_findings(self):
        """Empty findings list shows placeholder text."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        # No results added → findings list is empty → placeholder shown
        md = r.build()
        assert "## Follow-Up Candidates" in md
        assert "_No high-interest findings" in md or "No high-interest" in md

    def test_shows_top_5_by_interest_score(self):
        """Only top 5 interesting findings appear as follow-up candidates."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        for i in range(8):
            r.add_result({"title": f"Finding {i}", "content": "crack fail broken",
                          "platform": "web", "url": f"https://x.com/{i}"})
        md = r.build()
        assert "## Follow-Up Candidates" in md
        # Exactly 5 candidates shown (first 5 by interest score)
        candidate_count = md.count("/research")
        assert candidate_count == 5

    def test_includes_deepen_flag(self):
        """Follow-up candidates include the --deepen=<id> flag."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        r.add_result({"title": "License cracking surge", "content": "...",
                      "platform": "web", "url": "https://x.com/1"})
        md = r.build()
        assert "--deepen=" in md
        assert "finding-" in md  # finding ID is present

    def test_breaking_and_negative_rank_higher(self):
        """Breaking and negative findings rank higher in follow-up candidates."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        r.add_result({"title": "Neutral topic", "content": "general chat",
                      "platform": "web", "url": "https://x.com/1"})
        r.add_result({"title": "Critical bug found", "content": "crack exploit broken",
                      "platform": "web", "url": "https://x.com/2"})
        md = r.build()
        assert "## Follow-Up Candidates" in md
        # Both appear (neutral still makes the top-5 cut), but Critical bug (neg, score 2)
        # comes before Neutral topic (score 0)
        cand_section = md.split("## Follow-Up Candidates")[1].split("---")[0]
        bug_pos = cand_section.find("Critical bug found")
        neutral_pos = cand_section.find("Neutral topic")
        assert bug_pos != -1 and neutral_pos != -1
        assert bug_pos < neutral_pos

    def test_full_build_includes_follow_up_section(self):
        """Full report build includes ## Follow-Up Candidates section."""
        r = report.Report(topic="MQL5 cracking", project="lockingood",
                          platforms=["reddit", "web", "x"], days=30)
        r.add_result({"title": "Reddit post", "content": "crack discussion",
                       "platform": "reddit", "url": "https://r.com",
                       "author": "u", "score": 5, "num_comments": 2, "created_utc": 0, "permalink": ""})
        r.add_result({"title": "Web article", "content": "license bypass",
                       "platform": "web", "url": "https://w.com",
                       "score": 0.9, "published_date": "2026-04-01"})
        md = r.build()
        assert "## Follow-Up Candidates" in md


class TestPriorityRecommendations:
    def test_marketing_priority_puts_marketing_findings_first(self):
        """With priority=marketing, marketing-relevant findings rank first."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"],
                          days=30, priority="marketing")
        r.add_result({"title": "Bug in API", "content": "performance bug",
                      "platform": "web", "url": "https://x.com/1"})  # technical, negative
        r.add_result({"title": "Community growth", "content": "user adoption surge",
                      "platform": "web", "url": "https://x.com/2"})  # marketing, neutral
        recs = r._recommendations()
        # With marketing priority and only one negative, negative wins.
        # But if we have neg (bug) and marketing is not neg, marketing may rank lower.
        # Let's add a negative marketing finding too
        r2 = report.Report(topic="test", project="lockingood", platforms=["web"],
                           days=30, priority="marketing")
        r2.add_result({"title": "API bug", "content": "performance bug fail",
                       "platform": "web", "url": "https://x.com/1"})  # technical, negative
        r2.add_result({"title": "Crack spread", "content": "license crack community spread",
                       "platform": "web", "url": "https://x.com/2"})  # marketing+technical, negative
        recs2 = r2._recommendations()
        lines = recs2.split("\n")
        # Crack (marketing+technical, negative) should rank before pure technical bug
        crack_idx = next((i for i, l in enumerate(lines) if "Crack spread" in l), -1)
        api_idx = next((i for i, l in enumerate(lines) if "API bug" in l), -1)
        assert crack_idx != -1 and api_idx != -1
        assert crack_idx < api_idx  # marketing-relevant (crack/license) comes first

    def test_technical_priority_puts_technical_findings_first(self):
        """With priority=technical, technical findings rank first."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"],
                           days=30, priority="technical")
        r.add_result({"title": "Community hype", "content": "brand sentiment rising",
                      "platform": "web", "url": "https://x.com/1"})  # marketing, negative
        r.add_result({"title": "API crash", "content": "api performance latency error",
                      "platform": "web", "url": "https://x.com/2"})  # technical, negative
        recs = r._recommendations()
        lines = recs.split("\n")
        api_idx = next((i for i, l in enumerate(lines) if "API crash" in l), -1)
        hype_idx = next((i for i, l in enumerate(lines) if "Community hype" in l), -1)
        assert api_idx != -1 and hype_idx != -1
        assert api_idx < hype_idx  # technical (api crash) comes first for technical priority

    def test_general_priority_uses_negative_sentiment(self):
        """With priority=general, negative sentiment drives recommendations."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"],
                           days=30, priority="general")
        r.add_result({"title": "Good release", "content": "great new update",
                      "platform": "web", "url": "https://x.com/1"})  # positive
        r.add_result({"title": "Bug exposed", "content": "crack exploit fail",
                      "platform": "web", "url": "https://x.com/2"})  # negative
        recs = r._recommendations()
        assert "Bug exposed" in recs
        assert "Good release" not in recs

    def test_no_findings_returns_placeholder(self):
        """Empty report returns a placeholder recommendation."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"],
                           days=30, priority="marketing")
        recs = r._recommendations()
        assert "No findings available" in recs or "No immediate action" in recs

    def test_build_report_accepts_priority(self):
        """build_report() passes priority through to the Report object."""
        r = report.build_report(
            topic="test",
            project="lockingood",
            platforms=["web"],
            days=30,
            all_results=[],
            priority="marketing",
        )
        assert r.priority == "marketing"

    def test_priority_field_default_is_general(self):
        """Report.priority defaults to 'general' when not specified."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        assert r.priority == "general"


class TestChatDelivery:
    def test_build_chat_summary_no_findings(self):
        """Report with no findings produces a 'no results found' summary."""
        r = report.Report(topic="MQL5 cracking", project="lockingood",
                          platforms=["web"], days=30)
        # No results added
        chat = report.build_chat_summary(r)
        assert isinstance(chat, report.ChatDelivery)
        assert "no results found" in chat.summary
        assert chat.key_findings == []
        assert chat.obsidian_link == ""
        assert "## Follow-Up Candidates" in chat.markdown

    def test_build_chat_summary_with_findings(self):
        """Report with findings produces populated key_findings."""
        r = report.Report(topic="MQL5 cracking", project="lockingood",
                          platforms=["web"], days=30)
        r.add_result({"title": "Critical bug found", "content": "crack exploit broken",
                      "platform": "web", "url": "https://x.com/1"})
        r.add_result({"title": "New feature launched", "content": "great release",
                      "platform": "web", "url": "https://x.com/2"})
        r.add_result({"title": "General chat", "content": "just talking about stuff",
                      "platform": "web", "url": "https://x.com/3"})
        chat = report.build_chat_summary(r, obsidian_path="/vault/research/test.md")
        assert "MQL5 cracking" in chat.summary
        assert len(chat.key_findings) <= 5
        # Negative sentiment appears first in key_findings
        assert "[NEG]" in chat.key_findings[0] or "Critical" in chat.key_findings[0]
        assert chat.obsidian_link == "/vault/research/test.md"
        assert "Full report saved to Obsidian" in chat.obsidian_note
        assert isinstance(chat.markdown, str)
        assert "# Research: MQL5 cracking" in chat.markdown

    def test_obsidian_note_when_not_saved(self):
        """When obsidian_path is None, obsidian_note reflects that."""
        r = report.Report(topic="test", project="lockingood", platforms=["web"], days=30)
        r.add_result({"title": "T", "content": "...", "platform": "web", "url": "https://x.com"})
        chat = report.build_chat_summary(r, obsidian_path=None)
        assert chat.obsidian_link == ""
        assert "not saved" in chat.obsidian_note

    def test_chat_delivery_has_all_fields(self):
        """ChatDelivery dataclass has all required fields."""
        r = report.Report(topic="t", project="p", platforms=["web"], days=30)
        r.add_result({"title": "X", "content": "...", "platform": "web", "url": "https://x.com"})
        chat = report.build_chat_summary(r)
        assert hasattr(chat, "summary")
        assert hasattr(chat, "key_findings")
        assert hasattr(chat, "obsidian_link")
        assert hasattr(chat, "obsidian_note")
        assert hasattr(chat, "markdown")
        assert isinstance(chat.summary, str)
        assert isinstance(chat.key_findings, list)
        assert isinstance(chat.obsidian_link, str)
