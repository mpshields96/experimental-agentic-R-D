# PROJECT_INDEX.md — Titanium-Agentic
## Generated: Session 14, 2026-02-19 | 418/418 tests passing

**Read this file at session start instead of scanning the full codebase. ~94% token reduction.**
See CLAUDE.md for rules, MASTER_ROADMAP.md for task backlog, SESSION_LOG.md for history.

---

## 📁 Project Structure

```
agentic-rd-sandbox/
├── app.py                      Streamlit entry point, sidebar health, scheduler init
├── pages/
│   ├── 01_live_lines.py        Live bet pipeline — fetch → rank → card render
│   ├── 02_analysis.py          Analysis: KPIs, P&L, edge%, CLV, ROI, Line Pressure
│   ├── 03_line_history.py      Movement cards, sparklines, RLM seed table
│   ├── 04_bet_tracker.py       Log bets, grade outcomes, P&L, CLV per bet
│   └── 05_rd_output.py         R&D math dashboard + Pinnacle probe + CLV tracker
├── core/
│   ├── math_engine.py          ALL betting math (no API, no UI, no I/O)
│   ├── odds_fetcher.py         Odds API integration only
│   ├── line_logger.py          SQLite writes + schema (line_history.db)
│   ├── scheduler.py            APScheduler — polls + purges
│   ├── price_history_store.py  RLM 2.0 — persistent open-price SQLite store
│   ├── clv_tracker.py          CLV CSV persistence + verdict
│   ├── probe_logger.py         Pinnacle probe JSON log
│   ├── nhl_data.py             NHL goalie starter detection (free NHL API, zero quota cost)
│   └── efficiency_feed.py      Team efficiency data layer — 250+ teams, 10 leagues (no imports)
├── tests/
│   ├── test_math_engine.py     ~165 tests (incl. RLM, NHL kill switch, efficiency_gap wire-in)
│   ├── test_odds_fetcher.py    32 tests
│   ├── test_line_logger.py     31 tests
│   ├── test_scheduler.py       35 tests (incl. NHL goalie poll)
│   ├── test_price_history_store.py  36 tests
│   ├── test_clv_tracker.py     46 tests
│   ├── test_probe_logger.py    36 tests
│   ├── test_nhl_data.py        34 tests
│   └── test_efficiency_feed.py 53 tests  [TOTAL: 418]
├── data/
│   ├── line_history.db         SQLite — lines + bets (WAL mode)
│   ├── price_history.db        SQLite — RLM open prices (append-only)
│   ├── clv_log.csv             CLV snapshots
│   └── probe_log.json          Pinnacle probe history (rolling 200)
├── CLAUDE.md                   Master initialization prompt + rules
├── CONTEXT_SUMMARY.md          Architecture ground truth (update when arch changes)
├── SESSION_LOG.md              Per-session build diary
├── MASTER_ROADMAP.md           Canonical task backlog + kill switch specs
└── requirements.txt
```

---

## 🚀 Entry Points

| Path | Purpose |
|---|---|
| `app.py` | `streamlit run app.py` — launches full app on port 8501+ |
| `core/scheduler.py` | `start_scheduler()` called in app.py with session_state guard |
| `tests/` | `python3 -m pytest tests/` — all 314 tests |

---

## 📦 Core Modules

### `core/math_engine.py` — ALL BETTING MATH
**Rule**: No API calls, no UI, no file I/O. Import freely from any module.

| Function/Class | Purpose |
|---|---|
| `BetCandidate` | Dataclass — full bet candidate including kill_reason, sharp_score, nemesis |
| `passes_collar(odds)` | -180 to +150 check — NON-NEGOTIABLE |
| `implied_probability(odds)` | Raw (vig-inclusive) implied prob |
| `no_vig_probability(a, b)` | Removes vig from 2-outcome market |
| `calculate_edge(win_prob, odds)` | Edge = model_prob - market_implied |
| `fractional_kelly(win_prob, odds)` | 0.25x Kelly, hard caps at 2u/1u/0.5u |
| `calculate_sharp_score(edge, rlm, eff, sit)` | 0-100 composite: edge(40)+RLM(25)+eff(20)+sit(15) |
| `sharp_to_size(score)` | NUCLEAR_2.0U / STANDARD_1.0U / LEAN_0.5U |
| `nba_kill_switch(...)` | B2B rest + star absence + pace variance |
| `nfl_kill_switch(wind, total, ...)` | Wind >15/20mph thresholds |
| `ncaab_kill_switch(3pt, is_away, ...)` | 40% 3PT reliance on road |
| `soccer_kill_switch(drift, ...)` | 10% market drift |
| `nhl_kill_switch(backup_goalie, b2b, goalie_confirmed)` | Backup goalie KILL, B2B FLAG, unconfirmed FLAG |
| `consensus_fair_prob(team, market, side, books)` | Multi-book vig-free mean + std_dev |
| `cache_open_prices(games)` | Seed in-memory RLM cache (first-seen = open) |
| `compute_rlm(event_id, side, current, public)` | Returns (bool, drift). Increments fire counter. |
| `seed_open_prices_from_db(dict)` | Loads DB prices into memory (RLM cold-start fix) |
| `rlm_gate_status()` | {fire_count, gate, pct_to_gate, gate_reached} |
| `calculate_clv(open, close, bet)` | CLV as decimal (multiply by 100 for %) |
| `clv_grade(clv)` | EXCELLENT/GOOD/NEUTRAL/POOR |
| `run_nemesis(bet, sport)` | Stress-test bet against worst-case scenarios |
| `parse_game_markets(game, sport, nhl_goalie_status, efficiency_gap)` | Raw game dict → list[BetCandidate] (main pipeline entry) |

**Key constants**: `MIN_EDGE=0.035`, `MIN_BOOKS=2`, `KELLY_FRACTION=0.25`, `SHARP_THRESHOLD=45.0`, `COLLAR_MIN=-180`, `COLLAR_MAX=150`, `RLM_FIRE_GATE=20`

---

### `core/odds_fetcher.py` — API INTEGRATION
**Rule**: No math, no UI, no file I/O. Owns all Odds API calls.

| Function/Class | Purpose |
|---|---|
| `QuotaTracker` | Tracks x-requests-used/remaining/last from response headers |
| `quota` | Module-level instance — import for sidebar display |
| `SPORT_KEYS` | Friendly name → API key dict (NBA, NFL, NCAAB, NHL, MLB, 6 soccer) |
| `ACTIVE_SPORTS` | List of all 12 active sport names |
| `MARKETS` | Sport key → market string for API call |
| `fetch_game_lines(sport_key)` | Single-sport fetch with backoff |
| `fetch_batch_odds(sports)` | Multi-sport — scheduler's main entry point |
| `compute_rest_days_from_schedule(games)` | NBA B2B detection from timestamps (zero API cost) |
| `probe_bookmakers(raw_games)` | Surveys all book keys — Pinnacle detection |
| `available_sports()` | Returns list of SPORT_KEYS keys |

**PREFERRED_BOOKS order**: draftkings → fanduel → betmgm → betrivers → caesars
**Soccer note**: h2h+totals only — spreads return 422 on bulk endpoint.

---

### `core/line_logger.py` — SQLite PERSISTENCE
**Rule**: SQLite WAL mode. Thread-safe reads. One file = one job.

| Function | Purpose |
|---|---|
| `init_db(db_path)` | Creates tables if not exist. WAL mode. |
| `log_snapshot(games, sport, db_path)` | Bulk upsert from fetch — main scheduler call |
| `upsert_line(...)` | Single line upsert (called by log_snapshot) |
| `get_movements(sport, min_delta, db_path)` | Lines that moved > threshold |
| `get_line_history(event_id, team, db_path)` | Sparkline data per team |
| `get_open_prices_for_rlm(sport, db_path)` | Seed RLM cache from DB |
| `log_bet(...)` | Append bet to bets table |
| `update_bet_result(bet_id, result, close_price, db_path)` | Grade bet |
| `get_bets(filters, db_path)` | Retrieve bets with optional filters |
| `get_pnl_summary(db_path)` | P&L aggregate for Analysis tab |

**DB path default**: `data/line_history.db` (relative to sandbox root)

---

### `core/scheduler.py` — APSCHEDULER
**Rule**: Never import from UI. Guards via `_scheduler` module-level var.

| Function | Purpose |
|---|---|
| `start_scheduler(poll_interval_minutes, db_path)` | Starts APScheduler, registers jobs. Idempotent. |
| `stop_scheduler()` | Shuts down, sets _scheduler = None. Safe on None. |
| `trigger_poll_now(db_path)` | Manual poll — returns {sport: n_games} dict |
| `get_status()` | Full state dict: running, last_poll_time, errors, quota, rlm_gate |
| `is_running()` | Bool shortcut |
| `reset_state()` | Test isolation — clears all module-level state |

**APScheduler jobs**: `line_poll` (every 5min) + `weekly_purge` (weeks=1)
**Poll sequence per sport**: integrate_with_session_cache → inject_historical_prices → log_snapshot → probe_bookmakers → log_probe_result

---

### `core/price_history_store.py` — RLM 2.0
**Rule**: Append-only. INSERT OR IGNORE — open price NEVER overwritten.
**DB**: `data/price_history.db` (SEPARATE from line_history.db)

| Function | Purpose |
|---|---|
| `init_price_history_db(db_path)` | Schema init |
| `record_open_prices(event_id, sides, sport)` | INSERT OR IGNORE per side |
| `integrate_with_session_cache(games, sport)` | Scan games, persist new events |
| `inject_historical_prices_into_cache(games)` | Seeds math_engine RLM cache from DB |
| `purge_old_events(days_old, db_path)` | Housekeeping — returns rows deleted |
| `price_history_status()` | One-line status string for sidebar |

---

### `core/clv_tracker.py` — CLV PERSISTENCE
**CSV**: `data/clv_log.csv`. Thread-safe (append mode).

| Function | Purpose |
|---|---|
| `log_clv_snapshot(event_id, side, open, bet, close)` | Appends CLV entry |
| `read_clv_log(last_n)` | Returns list[dict] with type coercion |
| `clv_summary(entries)` | {n, avg_clv_pct, positive_rate, verdict, ...} |

**CLV_GATE = 30** entries before verdict is meaningful.
**Verdict tiers**: STRONG EDGE CAPTURE / MARGINAL / NO EDGE / INSUFFICIENT DATA

---

### `core/probe_logger.py` — PINNACLE PROBE LOG
**JSON**: `data/probe_log.json`. Rolling trim at 200 entries.

| Function | Purpose |
|---|---|
| `log_probe_result(probe_result, sport)` | Appends probe entry |
| `read_probe_log(last_n, sport)` | Filtered read |
| `probe_summary(entries)` | {n_probes, pinnacle_rate, all_books_seen, ...} |
| `probe_log_status()` | One-line for sidebar |

---

### `core/efficiency_feed.py` — TEAM EFFICIENCY DATA LAYER
**Rule**: NO imports from other core modules. Pure static data.
**Coverage**: 250+ teams across NBA, NCAAB, NFL, MLB, MLS, EPL, Bundesliga, Ligue1, Serie A, La Liga.

| Function | Purpose |
|---|---|
| `get_team_data(team_name)` | Returns raw dict {adj_em, league} or None. Checks canonical → alias → case-insensitive. |
| `get_efficiency_gap(home_team, away_team)` | Returns 0-20 scaled gap. 10.0 = even. >10 = home edge. Returns 8.0 if either unknown. |
| `list_teams(league=None)` | Canonical team names. Optional filter: "NBA", "NFL", "NCAAB", etc. |

**Scaling formula**: `gap = (home_adj_em - away_adj_em + 30) / 60 × 20`, clamped [0, 20].
**Unknown fallback**: `8.0` (below neutral — conservative, doesn't inflate unknown matchup scores).
**Alias support**: 70+ entries (NBA nicknames, NFL nicknames, soccer short forms e.g. "PSG", "Man City").

**Usage in pipeline**:
```python
from core.efficiency_feed import get_efficiency_gap
eff_gap = get_efficiency_gap(home_team, away_team)  # 0-20 float
bets = parse_game_markets(game, sport, efficiency_gap=eff_gap)
```

---

### `core/nhl_data.py` — NHL GOALIE STARTER DETECTION
**API**: `api-web.nhle.com` (free, public, no key, zero Odds API quota cost)
**Cache**: `_goalie_cache: dict[str, dict]` keyed by Odds API event_id

| Function | Purpose |
|---|---|
| `normalize_team_name(name)` | Odds API team name → NHL abbrev (all 32 teams) |
| `get_nhl_game_ids_for_date(date_str, session)` | Today's schedule → list of game dicts |
| `get_nhl_starters_for_game(game_id, session)` | Boxscore → confirmed starter data or None (FUT state) |
| `get_starters_for_odds_game(away, home, start_utc, session)` | High-level: name→abbrev→boxscore |
| `cache_goalie_status(event_id, status)` | Write to module cache (called by scheduler) |
| `get_cached_goalie_status(event_id)` | Read from cache (called by parse_game_markets) |
| `clear_goalie_cache()` | Testing utility |

**Timing gate**: Returns None if >90 min before game start (FUT state — starter not yet set)
**FUT state**: `playerByGameStats` absent in boxscore → returns None → caller applies FLAG

---

## 🗄️ Data Files

| File | Format | Written by | Read by |
|---|---|---|---|
| `data/line_history.db` | SQLite WAL | line_logger | line_logger, pages/01,02,03,04 |
| `data/price_history.db` | SQLite append-only | price_history_store | price_history_store, scheduler |
| `data/clv_log.csv` | CSV append | clv_tracker | clv_tracker, pages/04,05 |
| `data/probe_log.json` | JSON rolling | probe_logger | probe_logger, pages/05, app.py sidebar |

---

## 🧪 Test Coverage

| File | Tests | Key areas |
|---|---|---|
| test_math_engine.py | ~165 | All math functions, RLM fire counter, kill switches, NHL kill, efficiency_gap |
| test_odds_fetcher.py | 32 | Fetch, backoff, quota, probe_bookmakers |
| test_line_logger.py | 31 | Schema, upsert, movements, bets, P&L |
| test_scheduler.py | 35 | Start/stop, jobs, poll, purge, rlm_gate, NHL goalie poll |
| test_price_history_store.py | 36 | INSERT OR IGNORE, inject, purge |
| test_clv_tracker.py | 46 | Log, read, summary, verdict tiers |
| test_probe_logger.py | 36 | Log, read, summary, rolling trim |
| test_nhl_data.py | 34 | normalize_team_name, schedule, boxscore, FUT state, cache |
| test_efficiency_feed.py | 53 | get_team_data, get_efficiency_gap, list_teams, architecture checks |
| **TOTAL** | **418** | **All passing** |

---

## 🔗 Import Rules (enforce — prevents circular imports)

```
math_engine       ← no imports from other core modules
odds_fetcher      ← no imports from math_engine (circular risk)
line_logger       ← no imports from math_engine or odds_fetcher
price_history_store ← imports math_engine ONLY (for seed call)
clv_tracker       ← imports math_engine ONLY
probe_logger      ← no imports from core (self-contained)
nhl_data          ← no imports from other core modules (data-only)
efficiency_feed   ← no imports from other core modules (data-only)
scheduler         ← imports all (orchestrator — allowed)
pages/*           ← import from core.* only
app.py            ← imports from core.* only
```

---

## 🎨 UI Design System

| Token | Value | Use |
|---|---|---|
| Background | `#0e1117` | Page bg |
| Card surface | `#1a1d23` | Card bg |
| Border | `#2d3139` | Card borders |
| Amber (brand) | `#f59e0b` | Accent, size labels, progress bars |
| Green (positive) | `#22c55e` | Positive edge |
| Red (nuclear) | `#ef4444` | NUCLEAR signal |
| Plotly paper | `#0e1117` | paper_bgcolor |
| Plotly plot | `#13161d` | plot_bgcolor |

**Rendering rules**: `st.html()` for cards (inline styles only). `st.markdown(unsafe_allow_html=True)` for global CSS only. `st.navigation()` + `st.Page()` for nav (Streamlit 1.36+).

---

## ⚡ Active Sports (12)

NBA · NFL · NCAAF · NCAAB · NHL · MLB (Mar 27+) · EPL · Ligue1 · Bundesliga · Serie A · La Liga · MLS

Kill switches active for: NBA, NFL, NCAAB, all Soccer, NHL (goalie starter). MLB/NCAAF = collar-only (see MASTER_ROADMAP).

---

## 🔒 System Gates (do not act without these)

| Gate | Condition | Action |
|---|---|---|
| SHARP_THRESHOLD raise | RLM sidebar shows RAISE READY (≥20 fires) | Manually change 45→50 in math_engine.py |
| Pinnacle origination | probe_log shows pinnacle_present=True 3+ sessions | Add Pinnacle to PREFERRED_BOOKS |
| CLV verdict | ≥30 graded bets in clv_log.csv | Check verdict tier |
| Tennis activation | User approves tier + api-tennis.com $40/mo | Add to SPORT_KEYS + build kill switch |
| MLB kill switch | Apr 1 2026 with 1wk live data | Build mlb_kill_switch() |
| NHL kill switch | ✅ COMPLETE (Session 13) | nhl_data.py + nhl_kill_switch() + scheduler wired |

---

*Read MASTER_ROADMAP.md Section 9 for next session checklist.*
