# PROJECT_INDEX.md — Titanium-Agentic
## Generated: sc:index-repo | 2026-02-19 | 534/534 tests passing

**Read this file at session start instead of scanning the full codebase. ~94% token reduction.**
See CLAUDE.md for rules, MASTER_ROADMAP.md for task backlog, SESSION_LOG.md for history.

---

## Project Structure

```
agentic-rd-sandbox/
├── app.py                        # Streamlit entry point, scheduler init, nav
├── pages/
│   ├── 01_live_lines.py          # Bet pipeline, math breakdown, Log Bet button
│   ├── 02_analysis.py            # KPIs, P&L, edge/CLV histograms, line pressure
│   ├── 03_line_history.py        # Movement cards, sparklines, RLM seed table
│   ├── 04_bet_tracker.py         # Bet log, grading, P&L, CLV tracker
│   └── 05_rd_output.py           # Math validation dashboard (pure math_engine)
├── core/
│   ├── math_engine.py            # All math — collar, edge, Kelly, sharp score, RLM, CLV, nemesis
│   ├── odds_fetcher.py           # The Odds API wrapper, quota tracker, rest days
│   ├── line_logger.py            # SQLite WAL: lines, snapshots, bets, movements
│   ├── scheduler.py              # APScheduler: poll loop, NHL goalie hook, purge
│   ├── nhl_data.py               # NHL free API: goalie starter detection
│   ├── tennis_data.py            # Surface classification, player name normalization
│   ├── clv_tracker.py            # CLV snapshot CSV log + summary
│   ├── efficiency_feed.py        # Team efficiency data (static, embedded)
│   ├── price_history_store.py    # SQLite price history, 14-day purge
│   ├── probe_logger.py           # Bookmaker probe log (JSON)
│   └── data/__init__.py
├── tests/                        # 534 unit tests across 10 modules
├── data/
│   └── probe_log.json
├── logs/
├── CLAUDE.md                     # Session rules, tool call limits, stop mechanism
├── MASTER_ROADMAP.md             # Feature backlog by phase/gate
├── SESSION_LOG.md                # Per-session changelog
└── CONTEXT_SUMMARY.md            # Condensed project context
```

---

## Entry Points

- **App**: `app.py` — `streamlit run app.py` (default port 8501; dev on 8503)
- **Tests**: `pytest tests/` — 534 tests, ~0.7s
- **Scheduler**: auto-starts via `app.py` session_state guard on first Streamlit load

---

## Core Modules

### math_engine.py
- Path: `core/math_engine.py`
- Key constants: `MIN_EDGE=0.035`, `KELLY_FRACTION=0.25`, `SHARP_THRESHOLD=45.0`, `COLLAR_MIN=-180`, `COLLAR_MAX=+150`
- Key exports: `passes_collar`, `passes_collar_soccer`, `implied_probability`, `no_vig_probability`, `no_vig_probability_3way`, `calculate_edge`, `fractional_kelly`, `calculate_sharp_score`, `sharp_to_size`, `run_nemesis`, `parse_game_markets`, `compute_rlm`, `cache_open_prices`, `seed_open_prices_from_db`, `rlm_gate_status`, `calculate_clv`, `clv_grade`
- Kill switches: `nba_kill_switch`, `nfl_kill_switch`, `ncaab_kill_switch`, `soccer_kill_switch`, `nhl_kill_switch`, `tennis_kill_switch`
- Purpose: Single source of all betting math. No DB or API imports — pure functions only.

### odds_fetcher.py
- Path: `core/odds_fetcher.py`
- Key exports: `fetch_game_lines`, `fetch_batch_odds`, `fetch_active_tennis_keys`, `compute_rest_days_from_schedule`, `probe_bookmakers`, `available_sports`, `QuotaTracker`
- Purpose: The Odds API HTTP layer. Quota tracking, exponential backoff, rest-day computation.

### line_logger.py
- Path: `core/line_logger.py`
- DB: `line_history.db` (SQLite WAL)
- Key exports: `init_db`, `upsert_line`, `log_snapshot`, `get_movements`, `get_upcoming_movements`, `get_line_history`, `get_open_prices_for_rlm`, `log_bet`, `update_bet_result`, `get_bets`, `get_pnl_summary`, `count_snapshots`
- Purpose: Persistent store for line snapshots, movements, and bet log.

### scheduler.py
- Path: `core/scheduler.py`
- Key exports: `start_scheduler`, `stop_scheduler`, `trigger_poll_now`, `get_status`, `is_running`, `reset_state`
- Internal: `_poll_all_sports`, `_poll_nhl_goalies`, `_purge_old_price_history`
- Purpose: APScheduler wrapper; polls odds every N minutes, hooks NHL goalie check within 90-min game window.

### nhl_data.py
- Path: `core/nhl_data.py`
- Key exports: `get_starters_for_odds_game`, `get_nhl_starters_for_game`, `get_nhl_game_ids_for_date`, `normalize_team_name`, `cache_goalie_status`, `get_cached_goalie_status`
- Purpose: Free NHL Stats API — detects confirmed goalie starters, no quota cost.

### tennis_data.py
- Path: `core/tennis_data.py`
- Key exports: `surface_from_sport_key`, `is_tennis_sport_key`, `normalize_player_name`, `extract_last_name`, `surface_label`, `is_upset_surface`
- Purpose: Surface classification (hard/clay/grass) and player name normalization for tennis markets.

### clv_tracker.py
- Path: `core/clv_tracker.py`
- Key exports: `log_clv_snapshot`, `read_clv_log`, `clv_summary`, `print_clv_report`
- Storage: CSV at `logs/clv_log.csv`
- Purpose: Closing Line Value snapshot and summary reporting.

### efficiency_feed.py
- Path: `core/efficiency_feed.py`
- Key exports: `get_team_data`, `get_efficiency_gap`, `list_teams`
- Purpose: Static embedded team efficiency data — no external dependency.

### price_history_store.py
- Path: `core/price_history_store.py`
- DB: `price_history.db` (SQLite)
- Key exports: `init_price_history_db`, `record_open_prices`, `integrate_with_session_cache`, `get_historical_open_price`, `inject_historical_prices_into_cache`, `purge_old_events`, `get_all_open_prices`
- Purpose: Persistent open-price store for multi-session RLM continuity. Auto-purges events >14 days old.

### probe_logger.py
- Path: `core/probe_logger.py`
- Key exports: `log_probe_result`, `read_probe_log`, `probe_summary`, `probe_log_status`
- Storage: `data/probe_log.json`
- Purpose: Bookmaker availability probe log; tracks which books are seen per poll.

---

## Test Coverage

| Module | Test File | Tests |
|---|---|---|
| math_engine | test_math_engine.py | ~180 |
| odds_fetcher | test_odds_fetcher.py | ~55 |
| line_logger | test_line_logger.py | ~45 |
| scheduler | test_scheduler.py | ~35 |
| nhl_data | test_nhl_data.py | ~35 |
| clv_tracker | test_clv_tracker.py | ~45 |
| efficiency_feed | test_efficiency_feed.py | ~51 |
| price_history_store | test_price_history_store.py | ~35 |
| probe_logger | test_probe_logger.py | ~38 |
| tennis_data | test_tennis_data.py | ~55 |
| **Total** | | **534 / 534 passing** |

---

## Key Dependencies

- `streamlit` — UI framework (1.36+, uses `st.navigation` + `st.Page`)
- `APScheduler` — background polling scheduler
- `requests` — The Odds API HTTP calls
- `pandas` — Analysis tab dataframes
- `plotly` — Charts in analysis + R&D tabs
- `sqlite3` — Built-in; WAL mode for concurrent writes
- Python 3.13 (use `datetime.now(timezone.utc)` not `datetime.utcnow()`)

---

## Architecture Rules (Non-Negotiable)

- Package imports: `from core.math_engine import ...` (NOT root-level)
- NEVER import math_engine from odds_fetcher — circular import
- Streamlit: `st.html()` for full HTML; `st.markdown(unsafe_allow_html=True)` for global CSS only; inline styles in card renderers
- Scheduler: guarded by `st.session_state` to prevent restart on rerun
- SQLite WAL mode active — safe for concurrent scheduler + UI reads

## UI Design Tokens

- Brand: `#f59e0b` (amber) | Positive: `#22c55e` | Nuclear: `#ef4444`
- Background: `#0e1117` | Card: `#1a1d23` | Border: `#2d3139`
- Plotly: `paper_bgcolor="#0e1117"`, `plot_bgcolor="#13161d"`, `font.color="#d1d5db"`

## Math Invariants

- Collar: -180 to +150 (soccer expanded: -250 to +400)
- Min edge: 3.5%
- Min books for consensus: 2
- Kelly: 0.25x fraction; >60% → 2.0u, >54% → 1.0u, else → 0.5u
- SHARP_THRESHOLD = 45 (raise to 50-55 after RLM fires ≥20 times live)
- RLM trigger: 3% implied prob shift; passive until 2nd fetch

---

## Quick Start

```bash
cd ~/ClaudeCode/agentic-rd-sandbox
streamlit run app.py --server.port 8503
pytest tests/ -q
```
