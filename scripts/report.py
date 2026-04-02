"""
Report synthesis for last30research.
Takes raw platform results and produces a structured intelligence report.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    id: str
    title: str
    body: str
    sentiment: str  # positive | neutral | negative | mixed
    platforms: List[str]
    proof_quote: str
    proof_url: str
    is_new: bool = True
    first_seen: str = ""
    is_breaking: bool = False

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "Finding":
        title = result.get("title", "Untitled")
        fid = hashlib.md5(title.encode()).hexdigest()[:8]
        return cls(
            id=f"finding-{fid}",
            title=title[:120],
            body=result.get("content", result.get("selftext", ""))[:300],
            sentiment=_sentiment(result),
            platforms=[result.get("platform", "unknown")],
            proof_quote=_quote(result),
            proof_url=result.get("url", result.get("permalink", "")),
        )


def _sentiment(result: Dict[str, Any]) -> str:
    text = (result.get("title", "") + " " +
            (result.get("content") or result.get("selftext") or "")).lower()
    neg_kw = ["crack", "stolen", "broken", "fail", "bug", "exploit", "fake", "scam", "warning"]
    pos_kw = ["great", "love", "best", "awesome", "working", "fixed", "new release"]
    neg = sum(1 for kw in neg_kw if kw in text)
    pos = sum(1 for kw in pos_kw if kw in text)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def _quote(result: Dict[str, Any]) -> str:
    content = result.get("content") or result.get("selftext") or ""
    if not content:
        return "—"
    return '"' + content[:200].replace("\n", " ") + '"'


@dataclass
class Report:
    topic: str
    project: str
    platforms: List[str]
    days: int
    findings: List[Finding] = field(default_factory=list)
    web_results: List[Dict[str, Any]] = field(default_factory=list)
    reddit_results: List[Dict[str, Any]] = field(default_factory=list)
    x_results: List[Dict[str, Any]] = field(default_factory=list)
    hn_results: List[Dict[str, Any]] = field(default_factory=list)
    youtube_results: List[Dict[str, Any]] = field(default_factory=list)
    telegram_results: List[Dict[str, Any]] = field(default_factory=list)
    polymarket_results: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: str = ""
    previous_report: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def add_result(self, result: Dict[str, Any], finding: Optional[Finding] = None) -> None:
        """Add a raw result and optionally a pre-built Finding.

        If *finding* is provided it is used directly (caller controls deduplication
        metadata such as is_new). Otherwise a Finding is built from *result*.
        """
        platform = result.get("platform", "unknown")
        if platform == "web":
            self.web_results.append(result)
        elif platform == "reddit":
            self.reddit_results.append(result)
        elif platform == "x":
            self.x_results.append(result)
        elif platform == "hn":
            self.hn_results.append(result)
        elif platform == "youtube":
            self.youtube_results.append(result)
        elif platform == "telegram":
            self.telegram_results.append(result)
        elif platform == "polymarket":
            self.polymarket_results.append(result)

        # Use caller-supplied finding or build one from the raw result
        actual_finding = finding if finding is not None else Finding.from_result(result)
        self.findings.append(actual_finding)

    def build(self) -> str:
        """Render the report as a markdown string."""
        lines: List[str] = []

        lines.append(f"# Research: {self.topic}")
        lines.append(f"**Period:** Last {self.days} days | **Platforms:** {', '.join(self.platforms)}")
        lines.append(f"**Project:** {self.project} | **Generated:** {self.generated_at}")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(self._executive_summary())
        lines.append("")
        lines.append("## Key Findings")
        self._key_findings(lines)
        lines.append("")
        lines.append("## Platform Breakdown")
        self._platform_breakdown(lines)
        lines.append("")
        lines.append("## Sentiment & Consensus")
        lines.append(self._sentiment_section())
        lines.append("")
        lines.append("## Open Questions / Gaps")
        lines.append("_None identified._")
        lines.append("")
        lines.append("## Recommendations")
        lines.append(self._recommendations())
        lines.append("")
        lines.append(self._sources_footer())

        return "\n".join(lines)

    def _executive_summary(self) -> str:
        total = len(self.findings)
        platforms_found = len({f.platforms[0] for f in self.findings if f.platforms})
        if total == 0:
            return "No results found for this query across the selected platforms."
        return (
            f"Found {total} relevant results across {platforms_found} platforms in the last "
            f"{self.days} days. "
            f"Sentiment is predominantly **{self._overall_sentiment()}**. "
            f"Key themes include {self._top_theme()}. "
            f"{'Some findings appeared in the previous report and are marked as recurring.' if self._has_recurring() else 'All findings appear new compared to the previous report.'}"
        )

    def _has_recurring(self) -> bool:
        return any(not f.is_new for f in self.findings)

    def _overall_sentiment(self) -> str:
        if not self.findings:
            return "neutral"
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.sentiment] = counts.get(f.sentiment, 0) + 1
        return max(counts, key=counts.get)  # type: ignore

    def _top_theme(self) -> str:
        titles = " ".join(f.title for f in self.findings[:5])
        themes = {
            "license cracking": ["crack", "license", "bypass", "keygen"],
            "tool discussion": ["tool", "ea", "robot", "indicator"],
            "market trends": ["trend", "market", "signal", "strategy"],
            "product updates": ["update", "new release", "version", "launch"],
        }
        for theme, keywords in themes.items():
            if any(kw in titles.lower() for kw in keywords):
                return theme
        return "general discussion"

    def _key_findings(self, lines: List[str]) -> None:
        new = [f for f in self.findings if f.is_new and not f.is_breaking]
        breaking = [f for f in self.findings if f.is_breaking]
        recurring = [f for f in self.findings if not f.is_new]

        if breaking:
            lines.append("### 🆕 New / Breaking")
            for f in breaking[:5]:
                lines.append(self._finding_entry(f))
            lines.append("")

        if new:
            lines.append("### 📈 Emerging Trends")
            for f in new[:5]:
                lines.append(self._finding_entry(f))
            lines.append("")

        if recurring:
            lines.append("### 🔄 Recurring / Sustained")
            for f in recurring[:5]:
                lines.append(self._finding_entry(f))
            lines.append("")

        if not breaking and not new and not recurring:
            lines.append("_No significant findings._")

    def _finding_entry(self, f: Finding) -> str:
        status = "" if f.is_new else f" _(Prior report: {f.first_seen})_"
        badge = "⚠️ " if f.sentiment == "negative" else "📈 " if f.sentiment == "positive" else "💬 "
        platform_src = f.platforms[0] if f.platforms else "web"
        lines_entry = [
            f"- **{badge}{f.title}**{status}",
            f"  {f.body[:200]}",
            f"  _Proof:_ {platform_src} — {f.proof_quote[:150]}",
            f"  [Source]({f.proof_url})",
        ]
        return "\n".join(lines_entry)

    def _platform_breakdown(self, lines: List[str]) -> None:
        if self.reddit_results:
            lines.append("### Reddit")
            by_sub: Dict[str, List[Dict]] = {}
            for r in self.reddit_results:
                by_sub.setdefault(r.get("subreddit", "unknown"), []).append(r)
            for sub, posts in list(by_sub.items())[:3]:
                lines.append(f"- **r/{sub}:** {len(posts)} posts — _{posts[0]['title'][:80]}_")
            lines.append("")

        if self.web_results:
            lines.append("### Web / News")
            for r in self.web_results[:4]:
                lines.append(f"- [{r.get('title', 'Untitled')}]({r.get('url', '')})")
                lines.append(f"  {r.get('content', '')[:120]}")
            lines.append("")

        if self.x_results:
            lines.append("### X / Twitter")
            for r in self.x_results[:4]:
                lines.append(f"- {r.get('content', r.get('text', ''))[:120]} — *@{r.get('username', 'unknown')}*")
            lines.append("")

        if self.hn_results:
            lines.append("### Hacker News")
            for r in self.hn_results[:3]:
                lines.append(f"- [{r.get('title', 'Untitled')}]({r.get('url', '')}) — {r.get('score', 0)} points")
            lines.append("")

        if self.youtube_results:
            lines.append("### YouTube")
            for r in self.youtube_results[:3]:
                lines.append(f"- [{r.get('title', 'Untitled')}]({r.get('url', '')})")
            lines.append("")

        if self.telegram_results:
            lines.append("### Telegram")
            for r in self.telegram_results[:3]:
                lines.append(f"- {r.get('content', '')[:120]} — _via {r.get('channel', 'unknown')}_")
            lines.append("")

        if self.polymarket_results:
            lines.append("### Polymarket")
            for r in self.polymarket_results[:3]:
                lines.append(f"- {r.get('title', r.get('question', 'Unknown market'))} — {r.get('volume', 'N/A')} volume")
            lines.append("")

        if not any([self.reddit_results, self.web_results, self.x_results,
                    self.hn_results, self.youtube_results, self.telegram_results,
                    self.polymarket_results]):
            lines.append("_No results from enabled platforms._")

    def _sentiment_section(self) -> str:
        if not self.findings:
            return "No data available to assess sentiment."
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.sentiment] = counts.get(f.sentiment, 0) + 1
        total = len(self.findings)
        parts = [f"- **{k.title()}**: {v} ({v/total*100:.0f}%)" for k, v in counts.items()]
        return "\n".join(parts)

    def _recommendations(self) -> str:
        neg_findings = [f for f in self.findings if f.sentiment == "negative"]
        if neg_findings:
            recs = [f"- **{f.title[:80]}**: {f.body[:150]}" for f in neg_findings[:3]]
            return "\n".join(recs)
        return "- No immediate action items identified based on current findings."

    def _sources_footer(self) -> str:
        counts = [
            f"Reddit {len(self.reddit_results)}",
            f"Web {len(self.web_results)}",
            f"X {len(self.x_results)}",
            f"HN {len(self.hn_results)}",
            f"YouTube {len(self.youtube_results)}",
            f"Telegram {len(self.telegram_results)}",
            f"Polymarket {len(self.polymarket_results)}",
        ]
        active = [c for c in counts if not c.endswith(" 0")]
        return f"---\n*Sources:* [{' | '.join(active)}] | {len(self.findings)} findings | Generated {self.generated_at}"


# ── Public API ─────────────────────────────────────────────────────────────────

def build_report(
    topic: str,
    project: str,
    platforms: List[str],
    days: int,
    all_results: List[Dict[str, Any]],
    previous_report: Optional[Dict[str, Any]] = None,
) -> Report:
    """
    Build a structured Report from raw platform results.

    Parameters
    ----------
    topic:
        Research query topic.
    project:
        Project name (for context).
    platforms:
        List of platforms that were searched.
    days:
        Time window.
    all_results:
        Flat list of result dicts from all platform wrappers.
    previous_report:
        Dict representation of the previous report (for deduplication).

    Returns
    -------
    Report
        Render with :meth:`Report.build()` to get markdown.
    """
    report_obj = Report(
        topic=topic,
        project=project,
        platforms=platforms,
        days=days,
        previous_report=previous_report,
    )

    # Deduplicate against previous report and intra-run duplicates
    prev_finding_ids: set = set()
    if previous_report:
        for f in previous_report.get("findings", []):
            prev_finding_ids.add(f.get("id", ""))

    seen_ids: set = set()
    for result in all_results:
        finding = Finding.from_result(result)
        if finding.id in prev_finding_ids:
            finding.is_new = False
            finding.first_seen = previous_report.get("date", "unknown")
        if finding.id not in seen_ids:
            seen_ids.add(finding.id)
            report_obj.add_result(result, finding=finding)

    return report_obj
