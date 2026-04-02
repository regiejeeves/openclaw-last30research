# PRD: last30research — Multi-Platform Deep Research Skill

**Version:** 1.0  
**Date:** 2026-04-02  
**Author:** Jeeves  
**Status:** Draft  
**PRD Owner:** Gennady Matveev  

---

## 1. Concept & Vision

A configurable deep research skill that aggregates real-time insights from across the web's most active knowledge platforms — delivered as a structured intelligence report with key findings, references, and provenance. Designed to close the gap between "I should research this" and "I actually did it" by making the process frictionless enough to run regularly.

**Core promise:** One command, a few minutes, a polished report you'd otherwise never bother to compile.

**Personality:** A diligent research assistant who knows your projects, keeps quiet about what isn't new, and always shows his work.

---

## 2. Problem Statement

Currently, meaningful multi-platform research is not attempted because:
- Manual research across Reddit, X, Web, HN, YouTube, Telegram, and Polymarket is too time-consuming
- Synthesizing findings into a coherent intelligence report requires significant additional effort
- Results from different platforms don't talk to each other — duplicates go undetected, consensus is invisible
- Without a standardized output format, reports are hard to compare across time periods

This skill makes research frictionless enough to run per-project, per-campaign, or per-question — and produces output fit for stakeholder presentation.

---

## 3. User & Use Cases

### Primary User
**Gennady Matveev** — using the skill as a marketing aide for the Lockingood project, reporting findings to stakeholders.

### Secondary Use (future)
Research for personal projects with project-specific priorities (marketing considerations may not be primary for all projects).

### Core Use Cases

1. **Stakeholder briefing** — Run before a Lockingood update to understand what the community is discussing, what's new, what's broken, what's trending.
2. **Periodic intelligence** — Run weekly/monthly as part of project rhythm; compare reports to detect shifts.
3. **Opportunity discovery** — Drill into a specific finding from a report to get a deeper picture.
4. **Competitive awareness** — Track what alternatives to Lockingood are discussed, how, and by whom.

---

## 4. Design Decisions

### 4.1 Async + Parallel Execution
Research across different platforms runs concurrently, not sequentially. Each platform's wrapper fires independently; results aggregate when all complete. This keeps total runtime close to the slowest single platform, not the sum of all.

### 4.2 Chat Notification on Complete
When all platform results are in, the skill delivers the full report to the chat automatically. No need to wait inline; you get notified when it's ready.

### 4.3 Light Follow-Up via Session Context
The skill stores its last report in a session-scoped memory file (not a full database). When you ask a follow-up like "tell me more about the cracking tools finding," the skill can reference the previous report's findings by loading that memory file. Light implementation — no vector search, no retrieval pipeline. Just last-report context.

### 4.4 Platform Selection: Two-Tier Configuration

**Per-project default** (in `projects.yaml`): all platforms enabled by default.
```yaml
lockingood:
  default_platforms: [reddit, x, web, hn, youtube, telegram, polymarket]
personal:
  default_platforms: [reddit, x, web, hn, youtube, telegram, polymarket]
```

**Per-request override** (CLI flags):
```
/research MQL5 license cracking --platforms=reddit,x   # override project defaults
/research forex ea monetization --all                    # all platforms
/research trends --quick                                # fast mode: reddit, x, web only
```

### 4.5 One Project at a Time
A single research run reads context from one project. Multi-project simultaneous research is out of scope for v1.

### 4.6 Install Location
`~/.openclaw/workspace/skills/last30research/`

---

## 5. Data Sources

### Primary Platforms (default)

| Platform | Method | Auth Required |
|----------|--------|---------------|
| **Web Search** | Tavily API | API key (already configured) |
| **Reddit** | `praw` (read-only) | No |
| **X / Twitter** | `@steipete/bird` | CT0 + AUTH_TOKEN cookies |

### Supplementary Platforms

| Platform | Method | Auth Required |
|----------|--------|---------------|
| **Hacker News** | Tavily or direct scrape | No |
| **YouTube** | yt-dlp + Gemini transcription | No |
| **Telegram** | Bot forward or URL fetch | Bot token |
| **Polymarket** | Tavily + direct scrape | No |

---

## 6. Project Context Integration

### 6.1 Project Registry
A `projects.yaml` file maps project names to their context:

```yaml
projects:
  lockingood:
    research_context:
      - /path/to/lockingood/research/executive_brief.md
      - /path/to/lockingood/research/product_assumptions.md
    default_platforms: [reddit, x, web]
    domain_keywords: [mql5, metatrader, forex, license protection, ea protection, trading robot]
    priority: marketing  # signals that marketing considerations come first
  personal:
    research_context:
      - /path/to/personal/research/context.md
    default_platforms: [reddit, x, web, polymarket]
    priority: general
```

### 6.2 Context Loading Behavior
When `/research <query>` is invoked with a project flag:
1. Read each context file (up to 30 lines each, or full if under 2KB)
2. Extract domain keywords → inject into search queries
3. Load priority directive → rank findings accordingly (e.g., for Lockingood: marketing angle first, technical second)
4. Load previous report if one exists for this project (for deduplication — see 7.3)

### 6.3 Auto-Detection
If no project is specified, the skill attempts to match query keywords against known project domain keywords. Falls back to `general` project (no special context).

---

## 7. Output Format

### 7.1 Report Structure

```
# Research: <topic>
**Period:** Last 30 days | **Platforms:** Reddit, X, Web, HN
**Project:** Lockingood | **Generated:** 2026-04-02 18:30 MSK

## Executive Summary
2-3 sentences capturing the key narrative across all platforms.

## Key Findings

### 🆕 New / Breaking
- **[Finding title]** — [1-2 sentence explanation with platform provenance]
  *Proof:* [platform] — *"relevant quote or data point"*

### 📈 Emerging Trends
- **[Trend title]** — [explanation of why this is notable, how widespread]
  *Proof:* [platform × count] — *"representative quote"*

### 🔄 Recurring / Sustained
- **[Topic]** — [note if this appeared in previous report; new data since then]
  *Prior report:* 2026-03-15

### ⚠️ Risks / Concerns
- **[Risk]** — [community complaints, emerging threats, competitive shifts]

## Platform Breakdown

### Reddit
- **r/MT5:** [summary] — *"representative quote"*
- **r/algotrading:** [summary] — *"representative quote"*

### X / Twitter
- [summary] — *@user*
- [summary] — *@user*

### Web / News
- [summary] — *source*

## Sentiment & Consensus
[What the community agrees on vs. where it divides]

## Open Questions / Gaps
[Questions the research couldn't answer — these become follow-up candidates]

## Recommendations for Lockingood
[Prioritized by project priority directive — marketing angle for Lockingood]
[Specific, actionable, tied to findings above]

---
*Sources:* [Reddit 3] [X 5] [Web 4] [HN 2] | 14 queries executed | ~4min runtime
```

### 7.2 Obsidian Auto-Save
- **Default:** save to `research/` folder in project's vault
- **Path:** `<project_vault>/research/<slugified-topic>-<date>.md`
- **Flag:** `--no-save` suppresses save

### 7.3 Deduplication Against Previous Reports
If a previous report exists for the same project, the skill loads it and:
- Marks findings that appeared in the prior report as "Recurring / Sustained" rather than "New"
- Excludes verbatim repetition of findings unless the new data adds meaningful update
- Notes "First seen: [date]" on genuinely new findings

### 7.4 Follow-Up References
At the end of each report:
```
## Follow-Up Candidates
- `/research <topic> --deepen=<finding-id>` — drill into finding #N
- `/research <topic> --platforms=reddit,x --days=7` — refresh on specific platforms
```

The `--deepen` flag loads the previous report and uses the finding as a focused sub-query.

---

## 8. Configuration Reference

### 8.1 Per-Request Flags

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--platforms` | reddit,x,web,hn,youtube,telegram,polymarket | project default or all | Platforms to search |
| `--days` | 7/14/30/90 | 30 | Time window |
| `--project` | project name | auto-detect | Project context to load |
| `--save/--no-save` | bool | save | Auto-file to Obsidian |
| `--folder` | folder name | research | Obsidian destination |
| `--quick` | bool | false | Fast: reddit,x,web only, 2-3 min |
| `--deep` | bool | false | Full: all platforms, 5-8 min |
| `--deepen` | finding-id | none | Drill into a specific finding from last report |

### 8.2 Project-Level Config (projects.yaml)

```yaml
default_project: lockingood
default_platforms: [reddit, x, web, hn, youtube, telegram, polymarket]  # all enabled by default
default_days: 30
auto_save: true
default_folder: research
model: M2.7
tavily_depth: basic  # ultra-fast/fast/basic/advanced
```

---

## 9. Technical Architecture

### 9.1 Skill Structure

```
last30research/
├── SKILL.md                  # Skill invocation interface
├── docs/
│   └── PRD.md                 # This document
├── scripts/
│   ├── research.py            # Main orchestration (async gather)
│   ├── platform/
│   │   ├── reddit_search.py   # PRAW wrapper
│   │   ├── x_search.py        # Bird wrapper
│   │   ├── tavily_search.py   # Tavily API wrapper
│   │   ├── hn_search.py        # HN scraper
│   │   ├── youtube_search.py  # yt-dlp + Gemini
│   │   └── polymarket_search.py
│   └── report.py              # Report synthesis + formatting
├── config/
│   └── projects.yaml          # Project registry
└── references/
    └── platform_guide.md      # Per-platform search tips & auth docs
```

### 9.2 Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `praw` | Reddit read-only API | `uv add praw` |
| `@steipete/bird` | X / Twitter search | npm global |
| `yt-dlp` | YouTube transcript extraction | brew/youtube search project |
| `tavily-py` | Web search (already for Steve) | `uv add tavily-py` |

### 9.3 Async Execution Model

```
research.py (main)
  ├── reddit_search.py     ← asyncio.create_task
  ├── x_search.py          ← asyncio.create_task
  ├── tavily_search.py     ← asyncio.create_task
  ├── hn_search.py         ← asyncio.create_task
  └── youtube_search.py     ← asyncio.create_task (only if --deep)
  
  await asyncio.gather(*all_tasks) → aggregate → report.py → deliver to chat → save
```

### 9.4 Session Memory (Follow-Up)

After each research run, save to `~/.openclaw/workspace/memory/last30research/<project>-<date>.json`:
```json
{
  "project": "lockingood",
  "topic": "MQL5 license cracking",
  "date": "2026-04-02",
  "platforms": ["reddit", "x", "web"],
  "findings": [...],
  "report_path": "..."
}
```

On next `/research` with `--deepen`, load the most recent file for that project.

---

## 10. Out of Scope (v1)

- Code generation or modification based on findings
- Sending messages, emails, or notifications beyond the chat
- Multi-project simultaneous research
- Vector search / semantic retrieval over historical reports
- Persistent database of all past reports ( filesystem + Obsidian is the store)
- Automated iterative drilling (only manual follow-up via `--deepen`)

---

## 11. Success Criteria

1. **One command** produces a stakeholder-ready report with no additional prompting
2. **Platform coverage** across at least Reddit, X, and Web by default
3. **Deduplication** correctly identifies recurring vs. new findings vs. prior report
4. **Reference quality** — every key claim has a traceable source/quote
5. **Runtime** under 5 minutes for default (quick: under 3 min)
6. **Follow-up** finding reference works from session context

---

## 12. Open Questions (resolved)

| Question | Decision |
|----------|----------|
| Async or sync? | **Async** — parallel platform execution |
| Webhook/callback? | **Chat notification** — results delivered to active chat |
| Follow-up questions? | **Light** — session-scoped memory file, `--deepen` flag |
| Lite mode? | **Per-platform selection** — `--quick` flag + `--platforms` override |
| Multi-project? | **One at a time** — v1 scope |
| Install location? | **`~/.openclaw/workspace/skills/last30research/`** |

---

## 13. Next Steps

> [!important]
> **Toby must use GSD workflow** (`/gsd:new-project` → `/gsd:plan-phase` → `/gsd:execute-phase` → `/gsd:verify-work` → `/gsd:complete-milestone`) for all phase implementations. See: https://github.com/get-shit-done/gsd-claude-code

1. **PRD sign-off** — Gennady reviews and approves
2. **Assign to Toby** — Use `/gsd:new-project` to initialize, then build core: SKILL.md + research.py orchestration + Tavily wrapper
3. **Sisi review** — Code quality + test strategy
4. **Phase 1 build** — Reddit + Tavily wrappers + report synthesis (MVP)
5. **Phase 2** — X/Bird + deduplication + Obsidian save
6. **Phase 3** — YouTube + HN + `--deepen` follow-up
7. **Lockingood pilot** — Real research run with stakeholder-quality output
