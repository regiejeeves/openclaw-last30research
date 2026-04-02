"""
Report synthesis for last30research.
Takes raw platform results and produces a structured intelligence report.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    priority: str = "general"  # e.g. "marketing", "technical", "general"

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
        lines.append("## Follow-Up Candidates")
        lines.append(self._follow_up_candidates())
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

    # ── Priority-aware recommendation helpers ──────────────────────────────────

    _MARKETING_KW = ["community", "brand", "competitor", "user", "adoption",
                     "feedback", "review", "price", "cost", "license", "crack",
                     "bypass", "free", "alternative", "switching", "churn",
                     "testimonial", "discussion", "mention", "sentiment"]
    _TECHNICAL_KW = ["bug", "crash", "exploit", "api", "performance", "latency",
                    "reliability", "stability", "error", "fail", "breaking",
                    "security", "vulnerability", "patch", "update", "release"]

    def _is_marketing_finding(self, f: Finding) -> bool:
        text = (f.title + " " + f.body).lower()
        return any(kw in text for kw in self._MARKETING_KW)

    def _is_technical_finding(self, f: Finding) -> bool:
        text = (f.title + " " + f.body).lower()
        return any(kw in text for kw in self._TECHNICAL_KW)

    def _recommendations(self) -> str:
        """
        Rank and return recommendations based on project priority.

        For ``marketing`` priority: marketing-relevant findings first, then technical.
        For ``technical`` priority: technical findings first, then marketing.
        For ``general`` priority: all findings sorted by negative sentiment.

        Findings with ``sentiment == negative`` are always included; if none exist,
        all findings are considered.
        """
        if not self.findings:
            return "- No findings available to base recommendations on."

        priority = self.priority or "general"
        neg_findings = [f for f in self.findings if f.sentiment == "negative"]
        source_list = neg_findings if neg_findings else self.findings

        # Score each finding: higher score = higher priority for this project
        def score(f: Finding) -> tuple[int, int]:
            p_score = 0
            if priority == "marketing":
                p_score = (3 if self._is_marketing_finding(f) else
                           1 if self._is_technical_finding(f) else 2)
            elif priority == "technical":
                p_score = (3 if self._is_technical_finding(f) else
                           1 if self._is_marketing_finding(f) else 2)
            else:  # general
                p_score = 2
            # Within same priority bucket, negative sentiment wins
            s_score = 2 if f.sentiment == "negative" else 1
            return (p_score, s_score)

        ranked = sorted(source_list, key=score, reverse=True)
        recs = [f"- **{f.title[:80]}**: {f.body[:150]}" for f in ranked[:5]]
        return "\n".join(recs) if recs else "- No immediate action items identified."

    def _follow_up_candidates(self) -> str:
        """
        Generate suggested follow-up queries from the most interesting findings.

        Interesting = breaking, negative, or mixed sentiment. Ranked by interest score.
        Each candidate shows: finding title + formatted /research sub-query.
        """
        def interest_score(f: Finding) -> int:
            score = 0
            if f.is_breaking:
                score += 3
            if f.sentiment == "negative":
                score += 2
            elif f.sentiment == "mixed":
                score += 2
            if not f.is_new:  # recurring is interesting for drill-down
                score += 1
            return score

        candidates = sorted(self.findings, key=interest_score, reverse=True)[:5]
        if not candidates:
            return "_No high-interest findings to follow up on._"

        lines: List[str] = []
        for f in candidates:
            # Refine topic from finding title (strip to ~8 words)
            refined = " ".join(f.title.split()[:8])
            # Escape for markdown but keep readable
            lines.append(
                f"- **`{f.title[:60]}`** — "
                f"`/research {refined} --deepen={f.id} --project={self.project}`"
            )
        return "\n".join(lines)

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
    priority: str = "general",
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
    priority:
        Project priority directive ("marketing", "technical", "general").
        Used to rank recommendations appropriately.

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
        priority=priority,
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


# ── Chat delivery ───────────────────────────────────────────────────────────────

@dataclass
class ChatDelivery:
    """
    Structured result from :func:`deliver_report_to_chat`.
    Suitable for rendering in chat without parsing markdown.
    """
    summary: str          # One-line summary of the research run
    key_findings: List[str]  # Up to 5 key finding titles
    obsidian_link: str    # Path to saved Obsidian file (empty if not saved)
    obsidian_note: str    # Human-readable note about where the file was saved
    markdown: str         # Full report markdown (unchanged)


def build_chat_summary(report_obj: "Report", obsidian_path: str | None = None) -> ChatDelivery:
    """
    Build a structured :class:`ChatDelivery` from a populated ``Report``.

    Parameters
    ----------
    report_obj:
        A :class:`Report` that has had :meth:`Report.build()` called
        (so findings are finalised with IDs).
    obsidian_path:
        Path string of the saved Obsidian file, if any.

    Returns
    -------
    ChatDelivery
    """
    findings = report_obj.findings

    # One-line summary
    total = len(findings)
    if total == 0:
        summary = f"🔍 Research on \"{report_obj.topic}\" — no results found."
    else:
        sentiment = report_obj._overall_sentiment()
        summary = (
            f"🔍 Research on \"{report_obj.topic}\" — "
            f"{total} finding{'s' if total != 1 else ''}, "
            f"mostly **{sentiment}**. "
            f"Ran on {', '.join(report_obj.platforms)}."
        )

    # Top 5 key findings (highest interest score)
    def interest_score(f: Finding) -> int:
        s = 0
        if f.is_breaking:
            s += 3
        if f.sentiment == "negative":
            s += 2
        elif f.sentiment == "mixed":
            s += 2
        return s

    top = sorted(findings, key=interest_score, reverse=True)[:5]
    key_findings = [
        f"[{sentiment.upper()}] {f.title[:70]}"  # e.g. "[NEGATIVE] MQL5 license crack...
        for f, sentiment in [(f, f.sentiment[:3].upper()) for f in top]
    ]

    # Obsidian link
    if obsidian_path:
        obsidian_note = f"📝 Full report saved to Obsidian"
        obsidian_link = obsidian_path
    else:
        obsidian_note = "(not saved — use `--save` to persist the report)"
        obsidian_link = ""

    return ChatDelivery(
        summary=summary,
        key_findings=key_findings,
        obsidian_link=obsidian_link,
        obsidian_note=obsidian_note,
        markdown=report_obj.build(),
    )
