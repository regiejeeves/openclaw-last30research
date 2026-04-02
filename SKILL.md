# last30research — Multi-Platform Deep Research Skill

**Skill owner:** Gennady Matveev  
**Skill runner:** Toby (coding sub-agent)  
**Location:** `~/.openclaw/workspace/skills/last30research/`

---

## What It Does

Aggregates real-time insights from Reddit, X, Web (Tavily), HN, YouTube, Telegram, and Polymarket into a structured intelligence report.

**One command → stakeholder-ready report.**

---

## Invocation

```
/research <topic> [flags]
```

### Examples

```bash
/research MQL5 license cracking --project=lockingood
/research forex ea monetization --platforms=reddit,x --days=14
/research trends --quick
/research trends --deep
/research MQL5 cracking --deepen=finding-3
```

---

## Flags

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--project` | project name | auto-detect | Project context to load |
| `--platforms` | reddit,x,web,hn,youtube,telegram,polymarket | project default or all | Platforms to search |
| `--days` | 7/14/30/90 | 30 | Time window |
| `--save/--no-save` | bool | save | Auto-file to Obsidian |
| `--folder` | folder name | research | Obsidian destination |
| `--quick` | bool | false | Fast: reddit,x,web only, ~2min |
| `--deep` | bool | false | Full: all platforms, ~5min |
| `--deepen` | finding-id | none | Drill into a specific finding from last report |
| `--all` | bool | false | All platforms |

---

## Project Configuration

Projects are defined in `config/projects.yaml`:

```yaml
projects:
  lockingood:
    research_context:
      - /path/to/context.md
    default_platforms: [reddit, x, web]
    domain_keywords: [mql5, metatrader, forex, license protection]
    priority: marketing
  personal:
    default_platforms: [reddit, x, web, polymarket]
    priority: general

default_project: lockingood
default_days: 30
auto_save: true
default_folder: research
tavily_depth: basic
```

---

## Output

The skill produces a structured report with:
- Executive Summary
- Key Findings (New / Emerging / Recurring / Risks)
- Platform Breakdown
- Sentiment & Consensus
- Recommendations
- Follow-up Candidates

Reports are auto-saved to Obsidian at:
`<vault>/research/<slugified-topic>-<date>.md`

---

## Architecture

```
last30research/
├── SKILL.md
├── docs/PRD.md
├── scripts/
│   ├── research.py          # Main orchestrator
│   ├── report.py            # Report synthesis
│   ├── session_memory.py     # Follow-up context
│   └── platform/
│       ├── __init__.py
│       ├── tavily_search.py  # Web (Tavily API)
│       ├── reddit_search.py # Reddit (PRAW)
│       ├── x_search.py      # X/Twitter (@steipete/bird)
│       ├── hn_search.py     # HN scraper
│       ├── youtube_search.py # yt-dlp + Gemini
│       └── polymarket_search.py
├── config/
│   └── projects.yaml
└── tests/
    ├── test_research.py
    ├── test_report.py
    └── test_platforms.py
```

---

## Phase 1 MVP

- `research.py` — async orchestration
- `tavily_search.py` — Tavily web search
- `reddit_search.py` — Reddit via PRAW
- `report.py` — basic report synthesis
- `config/projects.yaml` — project registry

---

## Dependencies

| Package | Install |
|---------|---------|
| `praw` | `uv add praw` |
| `tavily-py` | `uv add tavily-py` |
| `@steipete/bird` | npm global |

---

## Session Memory (Follow-Up)

After each run, saves to `~/.openclaw/workspace/memory/last30research/<project>-<date>.json`.

On `--deepen`, loads the most recent report for that project and uses it as context.
