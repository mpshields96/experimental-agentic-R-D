# CONTEXT_SUMMARY.md — Titanium-Agentic
**Session 1 — 2026-02-18**
**Ground truth document. Update when architecture changes.**

---

## Project Mission
Build **Titanium-Agentic**: a personal sports betting analytics platform that expands
on Titanium V36.1. Built from scratch in `~/ClaudeCode/agentic-rd-sandbox/`.

---

## Architecture Overview

### Stack
| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | Streamlit (multi-page) | `app.py` entry point |
| Storage | SQLite (local) | `data/line_history.db` |
| Scheduler | APScheduler (in-process) | 5-min line history pulls |
| Charts | Plotly | Interactive, Streamlit-native |
| Python | Match Titanium env (3.11+) | |
| Hosting target | PythonAnywhere (later) | Local-first |

### File Structure
```
agentic-rd-sandbox/
├── CLAUDE.md
├── CONTEXT_SUMMARY.md         (this file)
├── SESSION_LOG.md
├── app.py                     (Streamlit entry point)
├── pages/
│   ├── 01_live_lines.py       (Tab 1 — Live Lines, Priority 2)
│   ├── 02_analysis.py         (Tab 2 — Analysis, Priority 4)
│   ├── 03_line_history.py     (Tab 3 — Line History, Priority 1)
│   ├── 04_bet_tracker.py      (Tab 4 — Bet Tracker, Priority 3)
│   └── 05_rd_output.py        (Tab 5 — R&D Output, Priority 5)
├── core/
│   ├── math_engine.py         (All betting math — Kelly, EV, CLV, RLM)
│   ├── odds_fetcher.py        (Odds API integration only)
│   ├── line_logger.py         (SQLite writes + schema)
│   └── scheduler.py           (APScheduler setup)
├── data/
│   └── line_history.db        (SQLite, auto-created)
├── tests/
│   ├── test_math_engine.py
│   ├── test_odds_fetcher.py
│   └── test_line_logger.py
├── logs/
│   └── error.log
└── requirements.txt
```

---

## Inherited Mathematical Rules (from V36.1 — NON-NEGOTIABLE)

### Core Signal
- **+EV is the only bet selection criterion**
- Edge detection: multi-book consensus vig-free mean = model probability
  - Step 1: collect vig-free prob from each book (both sides required)
  - Step 2: average them → consensus model probability
  - Step 3: find best available price at any single book
  - Step 4: edge = consensus_prob - implied(best_price)
- Minimum edge: **≥ 3.5%** (absolute floor)
- Minimum books for consensus: **≥ 2**

### Odds Collar
- American odds: **-180 to +150** only. Reject everything outside.

### Kelly Sizing (0.25x fractional)
- win_prob > 0.60 → cap 2.0 units (NUCLEAR)
- win_prob > 0.54 → cap 1.0 units (STANDARD)
- else → cap 0.5 units (LEAN)

### Sharp Score (0-100 composite)
| Component | Max pts | Formula |
|-----------|---------|---------|
| EDGE | 40 | (edge% / 10%) × 40, capped |
| RLM | 25 | 25 if RLM confirmed, else 0 |
| EFFICIENCY | 20 | caller-provided 0-20 scaled gap |
| SITUATIONAL | 15 | rest + injury + motivation + matchup, capped |

- **SHARP_THRESHOLD = 45** (require ~7.8% edge to pass)
- NUCLEAR ≥ 90 | STANDARD ≥ 80 | LEAN ≥ 75

### RLM (Reverse Line Movement)
- 3% implied probability shift threshold (NOT 5 cents raw)
- `_OPEN_PRICE_CACHE` module-level dict → cold on first run
- Fires on second `run_pipeline()` call within same session
- `public_on_side` heuristic: `price < -105` = public side

### CLV (Closing Line Value)
- Track consensus open vs closing price
- Positive CLV validates that we beat the closing line (predictive accuracy signal)

### Kill Switches (sport-specific)
- NBA: rest_disadvantage AND spread < -4 → KILL spread
- NFL: wind > 15mph AND total > 42 → FORCE_UNDER
- NCAAB: 3PT reliance > 40% AND away → KILL
- Soccer: market drift > 10% → KILL
- NHL/MLB: no kill switch (pass-through)

### Dedup + Diversity
- Never output both sides of the same market
- Max 10 bets total | Max 3 per sport | Max 60% concentration

---

## Key Architecture Decisions Inherited from V36.1
1. Multi-book consensus IS the edge signal (not single-book comparison)
2. Soccer bulk endpoint: h2h,totals only (spreads cause 422)
3. Player props NOT supported on bulk endpoint (API tier 422)
4. `_KILL_ROUTER` has no "nba" entry by design — NBA handled explicitly
5. `st.html()` for full HTML slates (not `st.markdown()` — Streamlit 1.54+ sandboxes it)
6. Inline styles only in card renderer (Streamlit strips `<style>` tags)
7. Circular import warning: never import `math_engine` from `odds_fetcher` (V36 lesson)

---

## New Capabilities vs V36.1 (Titanium-Agentic expansion)

### Priority 1 — Line History (NEW, not in V36)
- SQLite persistent storage: `data/line_history.db`
- APScheduler: pull every 5 minutes
- Delta detection: flag movement > 3 points
- Schema: sport, market, team, open_line, current_line, timestamp, movement_delta
- This enables CLV tracking and active RLM detection (not passive)

### Priority 2 — Live Lines (Clean V36 port)
- No V35 bugs (duplicate market sides, wrong model JSON, collar violations)
- Global bet ranking by edge%
- Collar logic respected

### Priority 3 — Bet Tracker (Rebuild)
- Reference: `~/Projects/bet-tracker/index.html` (localStorage-based single-file)
- Rebuild in Python/SQLite: log bets, outcomes, P&L
- Fields: team, bet_type, odds, stake, result, edge_pct, kelly_size, sport, matchup

### Priority 4 — Analysis (depends on line history data)
- CLV tracking over time
- RLM detection visualization (active, from line_history.db)
- Edge% distribution charts
- ROI by bet type, sport, time period

### Priority 5 — R&D Output Display
- Model parameter comparisons
- Backtest result visualization
- Mathematical foundation validation dashboard

---

## Available Tools (Plugin Audit)
| Tool | Status | Use |
|------|--------|-----|
| Context7 MCP | ✅ Available | Live library documentation lookups |
| SuperClaude (sc:*) | ✅ Available | Architect, debugger, implement personas |
| Playwright MCP | ✅ Available | Browser automation (not needed for build) |
| Supabase MCP | ✅ Available | Future storage upgrade path |
| GitHub MCP | ❌ Not installed | Use Bash git commands only |

---

## What's Different from V36 R&D
- V36 root-level imports: `from edge_calculator import` / `from odds_fetcher import`
- Titanium-Agentic uses package imports: `from core.math_engine import` / `from core.odds_fetcher import`
- V36 data is in `data/` subfolder with `__init__.py` — same pattern here
- V36 R&D had no persistent line history — this is the primary new capability
- V36 used `calculate_edges()` as the unified entry point — same here via `core.math_engine`

---

## Known Risks / Constraints
- API key must come from `os.environ.get("ODDS_API_KEY")` — never hardcode
- APScheduler in-process: must handle app restarts (load existing DB on init)
- SQLite: not thread-safe without WAL mode — enable `PRAGMA journal_mode=WAL`
- Streamlit reruns on every interaction: scheduler must not restart on rerun
  - Solution: use `st.session_state` to track if scheduler is already running

---

## Session Build State
| Session | Built | Tests | Committed |
|---------|-------|-------|-----------|
| 1 | In progress | — | — |
