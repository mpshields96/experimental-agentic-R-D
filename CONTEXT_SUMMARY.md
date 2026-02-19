# CONTEXT_SUMMARY.md — Titanium-Agentic
**Ground truth document. Update when architecture changes.**
**Last updated: Session 14, 2026-02-19**

---

## Project Mission
Build **Titanium-Agentic**: a personal sports betting analytics platform that expands
on Titanium V36.1. Built from scratch in `~/ClaudeCode/agentic-rd-sandbox/`.
Running in parallel with titanium-v36 (production) and titanium-experimental (R&D).
Read-only reference of those folders is permitted. NO writes, NO modifications.

---

## Architecture Overview

### Stack
| Layer | Technology | Notes |
|---|---|---|
| Frontend | Streamlit 1.36+ | `app.py` entry point, st.navigation() + st.Page() |
| Storage | SQLite WAL | `data/line_history.db` + `data/price_history.db` |
| Scheduler | APScheduler 3.10+ | In-process, 5-min polls + weekly purge |
| Charts | Plotly | Interactive, dark theme |
| Python | 3.13 | datetime.now(timezone.utc) — not utcnow() |
| Hosting target | Local-first | PythonAnywhere eventually |

### File Structure (current — Session 14)
```
agentic-rd-sandbox/
├── CLAUDE.md                    Master init prompt + rules (updated S14)
├── CONTEXT_SUMMARY.md           This file
├── SESSION_LOG.md               Build diary (Session 1-14)
├── MASTER_ROADMAP.md            Task backlog + kill switch specs (updated S14)
├── PROJECT_INDEX.md             Codebase map — read this at session start (created S12)
├── requirements.txt
├── app.py                       Entry point + sidebar health dashboard
├── pages/
│   ├── 01_live_lines.py         Full bet pipeline, efficiency_gap wired, sort by sharp_score (S14)
│   ├── 02_analysis.py           6 panels: KPIs, P&L, edge%, CLV hist, ROI, Line Pressure
│   ├── 03_line_history.py       Movement cards, sparklines, RLM seed table
│   ├── 04_bet_tracker.py        Log/grade bets, P&L, CLV wire-in
│   └── 05_rd_output.py          7 panels: math validation + Pinnacle probe + CLV tracker
├── core/
│   ├── math_engine.py           All math (S1, S11, S14 — efficiency_gap param added)
│   ├── odds_fetcher.py          Odds API (S1, S7 — Pinnacle probe added)
│   ├── line_logger.py           SQLite persistence (S1)
│   ├── scheduler.py             APScheduler orchestrator (S2, S8-S11, S13 — NHL poll)
│   ├── price_history_store.py   RLM 2.0 persistent open prices (S8)
│   ├── clv_tracker.py           CLV CSV persistence (S7)
│   ├── probe_logger.py          Pinnacle probe JSON log (S9)
│   ├── nhl_data.py              NHL goalie starter detection — free NHL API (S13)
│   └── efficiency_feed.py       Team efficiency data — 250+ teams, 10 leagues (S14)
├── tests/ (9 test files, 418 tests, all passing)
└── data/
    ├── line_history.db           Lines + bets (1,149 rows as of S14)
    ├── price_history.db          RLM open prices (INSERT OR IGNORE)
    ├── clv_log.csv               CLV snapshots (0 entries — gate not met)
    └── probe_log.json            Pinnacle probe history
```

---

## Inherited Mathematical Rules (from V36.1 — NON-NEGOTIABLE)

### Core Signal
- **+EV is the only bet selection criterion**
- Edge = multi-book consensus vig-free mean - implied(best_price)
- Minimum edge: **≥ 3.5%** | Minimum books: **≥ 2**

### Odds Collar
- **-180 to +150 only.** Reject everything outside.

### Kelly Sizing (0.25x fractional)
- win_prob > 0.60 → cap 2.0u (NUCLEAR) | > 0.54 → 1.0u (STANDARD) | else → 0.5u (LEAN)

### Sharp Score (0-100)
| Component | Max | Formula |
|---|---|---|
| EDGE | 40 | (edge% / 10%) × 40 |
| RLM | 25 | 25 if confirmed, else 0 |
| EFFICIENCY | 20 | Caller-provided 0-20 |
| SITUATIONAL | 15 | rest+injury+motivation+matchup, capped |

- **SHARP_THRESHOLD = 45** | NUCLEAR ≥ 90 | STANDARD ≥ 80 | LEAN < 80 (no floor — anything above SHARP_THRESHOLD qualifies)
- Without RLM: ceiling ~75. STANDARD/NUCLEAR require RLM signal.

### RLM (Reverse Line Movement)
- 3% implied prob shift threshold
- `public_on_side` heuristic: price < -105
- `_OPEN_PRICE_CACHE` in math_engine — cold on process start
- **RLM 2.0**: `price_history_store.py` — SQLite, INSERT OR IGNORE, persists across restarts
- **RLM Fire Counter**: `_rlm_fire_count` in math_engine — increments on True return
- **RLM_FIRE_GATE = 20**: raise SHARP_THRESHOLD 45→50 MANUALLY when gate reached

### CLV (Closing Line Value)
- Tracks open vs close price. Validates predictive accuracy.
- **CLV_GATE = 30** entries before verdict meaningful.

### Kill Switches
| Sport | Trigger | Type |
|---|---|---|
| NBA | B2B rest + spread < 4 | KILL spread |
| NBA | B2B (no spread criterion) | FLAG — Kelly -50% |
| NBA | star absent + spread inside avg_margin | KILL |
| NBA | pace_std_dev > 4 + total market | KILL total |
| NFL | wind > 20mph | KILL all totals |
| NFL | wind > 15mph + total > 42 | FORCE_UNDER |
| NFL | backup_qb | KILL |
| NCAAB | 3PT > 40% + away | KILL |
| NCAAB | tempo_diff > 10 + total | KILL total |
| Soccer | market_drift > 10% | KILL |
| Soccer | dead rubber | KILL |
| NHL | backup_goalie confirmed | KILL (require 12%+ edge override) |
| NHL | b2b | FLAG — Kelly -50% |
| NHL | goalie not confirmed within 90min | FLAG — require 8%+ edge |
| MLB | (not built yet) | Apr 1 gate — MASTER_ROADMAP 3B |
| Tennis | (not built yet) | api-tennis.com $40/mo gate — MASTER_ROADMAP 3C |

---

## Import Rules (critical — prevents circular imports)
```
math_engine       ← nothing from core/
odds_fetcher      ← nothing from math_engine (circular risk — confirmed V36 bug)
line_logger       ← nothing from math_engine or odds_fetcher
price_history_store ← math_engine ONLY
clv_tracker       ← math_engine ONLY
probe_logger      ← nothing from core
nhl_data          ← nothing from core (data-only)
efficiency_feed   ← nothing from core (data-only)
scheduler         ← all of the above (orchestrator — only exception)
pages/*           ← from core.* only
```

---

## New Capabilities vs V36.1

| Feature | Status | Notes |
|---|---|---|
| SQLite line history | ✅ | WAL mode, delta detection, 5-min polls |
| RLM 2.0 persistent | ✅ | price_history_store.py — INSERT OR IGNORE |
| CLV tracking | ✅ | clv_tracker.py — CSV accumulation, 30-entry gate |
| Pinnacle probe | ✅ | probe_logger.py — rolling JSON, scheduler-wired |
| RLM fire gate | ✅ | _rlm_fire_count → sidebar RAISE READY badge |
| Weekly purge | ✅ | purge_old_events() via APScheduler weekly_purge job |
| Sidebar health | ✅ | Probe, price history, CLV, RLM gate cards |
| Bet tracker | ✅ | Log, grade, P&L, CLV per bet |
| Analysis page | ✅ | 6 panels, all with graceful empty states |
| R&D Output | ✅ | 7 panels, math validation + live probe + CLV |
| NHL kill switch | ✅ | nhl_data.py + nhl_kill_switch() + scheduler wired (S13) |
| Efficiency component (Sharp Score) | ✅ | efficiency_feed.py, 250+ teams, 10 leagues (S14) |
| MLB kill switch | ⏳ | Apr 1 gate — endpoint verified (MASTER_ROADMAP 3B) |
| Tennis | ⏳ | api-tennis.com $40/mo gate (MASTER_ROADMAP 3C) |

---

## Available Tools
| Tool | Status | Use |
|---|---|---|
| Context7 MCP | ✅ | Live library docs |
| SuperClaude (sc:*) | ✅ | implement, test, analyze, index-repo |
| Playwright MCP | ✅ | Browser automation (not needed for build) |
| Supabase MCP | ✅ | Future storage upgrade |
| Task (subagent) | ✅ | Background research, parallel work |
| GitHub MCP | ❌ | Use Bash git only |

---

## UI Design System
- Background: `#0e1117` | Card: `#1a1d23` | Border: `#2d3139`
- Brand amber: `#f59e0b` | Positive: `#22c55e` | Nuclear: `#ef4444`
- Plotly: `paper_bgcolor="#0e1117"`, `plot_bgcolor="#13161d"`, `font.color="#d1d5db"`
- `st.html()` for cards (inline styles only)
- `st.markdown(unsafe_allow_html=True)` for global CSS only
- `st.navigation()` + `st.Page()` for programmatic nav

---

## Session Build State
| Session | Built | Tests | Commit |
|---|---|---|---|
| S1 | math_engine, odds_fetcher, line_logger | 154 | 7853fca |
| S2 | scheduler, app.py, pages/01-05 scaffolds | 180 | a070e22 |
| S3 | bet_tracker full, Log Bet button | 180 | 3f83b2c |
| S4 | analysis page (6 panels), market_type fix | 180 | ef7158d |
| S5 | rd_output page (7 panels) | 180 | 2656d10 |
| S6 | Context sync, v36 read-only survey | 180 | a11a3a2 |
| S7 | CLV tracker, Pinnacle probe | 226 | 1ebf380 |
| S8 | price_history_store (RLM 2.0) | 262 | c818075 |
| S9 | probe_logger, scheduler probe wire-in | 298 | afd703c |
| S10 | Sidebar health dashboard, weekly purge | 302 | 3ade35b |
| S11 | RLM fire gate counter, DB path fix | 314 | 8eb9ed7 |
| S12 | Sports audit, API research, MASTER_ROADMAP, PROJECT_INDEX, CLAUDE.md | 314 | 472c4a3 |
| S13 | NHL kill switch: nhl_data.py + nhl_kill_switch() + scheduler NHL poll | 363 | 2c5fe4c |
| S14 | efficiency_feed.py (Sharp Score efficiency live) + W6 tennis confirmed | 418 | 15b261d |
