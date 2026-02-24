# PROJECT_INDEX.md — Titanium-Agentic
## Generated: sc:index-repo | 2026-02-24 | 1011/1011 tests passing

**Read this file at session start instead of scanning the full codebase. ~94% token reduction.**
See CLAUDE.md for rules, MASTER_ROADMAP.md for task backlog, SESSION_LOG.md for history.

---

## Project Structure

```
agentic-rd-sandbox/
├── app.py                          # Streamlit entry point, scheduler init, nav
├── pages/
│   ├── 01_live_lines.py            # Bet pipeline, math breakdown, Log Bet, KOTC sidebar
│   ├── 02_analysis.py              # KPIs, P&L, edge/CLV histograms, line pressure
│   ├── 03_line_history.py          # Movement cards, sparklines, RLM seed table
│   ├── 04_bet_tracker.py           # Bet log, grading, P&L, CLV tracker
│   ├── 05_rd_output.py             # Math validation dashboard (pure math_engine)
│   └── 06_simulator.py             # Trinity game simulator (NBA/Soccer Poisson mode)
├── core/
│   ├── math_engine.py              # ALL math — collar, edge, Kelly, sharp score, RLM, CLV, Nemesis
│   ├── odds_fetcher.py             # Odds API wrapper, quota tracker, rest days
│   ├── line_logger.py              # SQLite WAL: lines, snapshots, bets, movements
│   ├── scheduler.py                # APScheduler: poll loop, NHL goalie hook, purge
│   ├── nhl_data.py                 # Free NHL API: goalie starter detection
│   ├── tennis_data.py              # Surface classification, player name normalization, win rates
│   ├── efficiency_feed.py          # Static team efficiency data (250+ teams, 10 leagues)
│   ├── weather_feed.py             # NFL live wind (Open-Meteo, 32 stadiums, 1hr cache)
│   ├── originator_engine.py        # Trinity Monte Carlo simulation (20%C/20%F/60%M)
│   ├── parlay_builder.py           # 2-leg positive-EV parlay finder
│   ├── injury_data.py              # Static positional impact table (5 sports, 50+ positions)
│   ├── nba_pdo.py                  # NBA PDO regression signal (nba_api, 1hr TTL, _endpoint_factory)
│   ├── king_of_the_court.py        # DraftKings Tuesday KOTC analyzer (PRA-ranked)
│   ├── calibration.py              # Sharp score calibration pipeline (activates at 30 bets)
│   ├── clv_tracker.py              # CLV snapshot CSV log + summary
│   ├── price_history_store.py      # SQLite open-price store, 14-day purge, multi-session RLM
│   ├── probe_logger.py             # Bookmaker probe log (JSON)
│   └── data/__init__.py
├── scripts/
│   └── backup.sh                   # Session-end backup: sandbox + V36 → .backups/ (keep last 5)
├── tests/                          # 1011 unit tests across 17 test files
├── data/
│   └── (probe_log.json — gitignored)
├── logs/
├── CLAUDE.md                       # Session rules, tool call limits, stop mechanism
├── MASTER_ROADMAP.md               # Feature backlog by phase/gate
├── SESSION_LOG.md                  # Per-session changelog
└── CONTEXT_SUMMARY.md              # Condensed project context
```

---

## Entry Points

- **App**: `app.py` — `streamlit run app.py --server.port 8504`
- **Tests**: `python3 -m pytest tests/ -q` — 1007 tests, ~1.5s
- **Scheduler**: auto-starts via `app.py` session_state guard on first Streamlit load

---

## Core Modules

### math_engine.py
- Path: `core/math_engine.py`
- Key constants: `MIN_EDGE=0.035`, `KELLY_FRACTION=0.25`, `SHARP_THRESHOLD=45.0`, `COLLAR_MIN=-180`, `COLLAR_MAX=+150`
- Key exports: `passes_collar`, `passes_collar_soccer`, `implied_probability`, `no_vig_probability`, `no_vig_probability_3way`, `consensus_fair_prob_3way`, `calculate_edge`, `fractional_kelly`, `calculate_sharp_score`, `sharp_to_size`, `run_nemesis`, `parse_game_markets`, `compute_rlm`, `cache_open_prices`, `seed_open_prices_from_db`, `rlm_gate_status`, `calculate_clv`, `clv_grade`
- Kill switches: `nba_kill_switch`, `nfl_kill_switch`, `ncaab_kill_switch`, `soccer_kill_switch`, `nhl_kill_switch`, `tennis_kill_switch`, `nba_b2b_adjustment`, `ncaaf_kill_switch`
- parse_game_markets() params: `sport`, `nhl_goalie_status`, `efficiency_gap`, `tennis_sport_key`, `rest_days`, `wind_mph`, `nba_pdo`
- Purpose: Single source of all betting math. No DB or API imports — pure functions only.

### odds_fetcher.py
- Path: `core/odds_fetcher.py`
- Key exports: `fetch_game_lines`, `fetch_batch_odds`, `fetch_active_tennis_keys`, `compute_rest_days_from_schedule`, `probe_bookmakers`, `available_sports`, `QuotaTracker`, `quota`
- Purpose: The Odds API HTTP layer. Quota tracking, exponential backoff, rest-day computation.

### line_logger.py
- Path: `core/line_logger.py`
- DB: `data/line_history.db` (SQLite WAL)
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
- Purpose: Free NHL Stats API — detects confirmed goalie starters, zero Odds API quota cost.

### tennis_data.py
- Path: `core/tennis_data.py`
- Key exports: `surface_from_sport_key`, `is_tennis_sport_key`, `normalize_player_name`, `extract_last_name`, `surface_label`, `is_upset_surface`, `get_player_surface_rate`, `surface_mismatch_severity`, `get_surface_risk_summary`
- Data: ATP_SURFACE_WIN_RATES (48 entries), WTA_SURFACE_WIN_RATES (42 entries)
- Purpose: Surface classification + player win-rate lookup for tennis kill switch.

### efficiency_feed.py
- Path: `core/efficiency_feed.py`
- Key exports: `get_team_data`, `get_efficiency_gap`, `list_teams`
- Coverage: 250+ teams, 10 leagues (NBA/NCAAB/NFL/MLB/MLS/EPL/Bundesliga/Ligue1/SerieA/LaLiga)
- Purpose: Static embedded team efficiency data — zero external dependency.

### weather_feed.py
- Path: `core/weather_feed.py`
- Key exports: `get_stadium_wind`, `NFL_STADIUMS`
- Source: Open-Meteo free API, 32 NFL stadiums, 1hr cache
- Purpose: NFL wind data for totals kill switch (>20mph KILL, >15mph FORCE_UNDER).

### originator_engine.py
- Path: `core/originator_engine.py`
- Key exports: `efficiency_gap_to_margin`, `run_trinity_simulation`, `SimulationResult`
- Formula: 20% consensus + 20% first-principles + 60% Monte Carlo
- Purpose: Trinity game simulator — cover probability for spread/total bets.

### parlay_builder.py
- Path: `core/parlay_builder.py`
- Key exports: `american_to_decimal`, `parlay_ev`, `parlay_kelly`, `build_parlay_combos`, `format_parlay_summary`, `ParlayCombo`
- Rules: 2-leg max, same-event/matchup/KILL blocked, same-sport 5% EV haircut
- Purpose: Finds positive-EV parlay combinations from current BetCandidate list.

### injury_data.py
- Path: `core/injury_data.py`
- Key exports: `injury_kill_switch`, `evaluate_injury_impact`, `list_high_leverage_positions`, `InjuryReport`
- Coverage: 5 sports (NBA/NFL/NHL/MLB/Soccer), 50+ positions, NCAAB→NBA / NCAAF→NFL aliases
- Thresholds: KILL ≥3.5pt | FLAG ≥2.0pt | silence below
- Purpose: Static positional impact table — no unofficial API, zero quota cost.

### nba_pdo.py
- Path: `core/nba_pdo.py`
- Key exports: `compute_pdo`, `classify_pdo`, `get_all_pdo_data`, `get_team_pdo`, `pdo_kill_switch`, `normalize_nba_team_name`, `clear_pdo_cache`, `PdoResult`
- Source: nba_api.stats.endpoints.LeagueDashTeamStats — free, no key, 1hr TTL
- Injection: `_endpoint_factory` param — zero network in tests (no unittest.mock.patch)
- Baseline: PDO=100.0; REGRESS≥102 | RECOVER≤98 | NEUTRAL 98-102
- Kill: REGRESS+WITH=KILL | RECOVER+AGAINST=KILL | totals exempt
- Edge case: normalize_nba_team_name maps "LA Clippers" → "Los Angeles Clippers"
- Purpose: PDO regression signal — fades teams running hot/cold on luck.

### king_of_the_court.py
- Path: `core/king_of_the_court.py`
- Key exports: `rank_kotc_candidates`, `get_kotc_top_pick`, `format_kotc_summary`, `is_kotc_eligible_day`, `KotcCandidate`
- Data: 55 player profiles (2025-26 season averages), 30-team defensive ratings
- Virtual profile: "Tyrese Maxey-Embiid-out" activates when Embiid confirmed DNP
- Score: 60% PRA projection + 30% ceiling + 10% TD threat + matchup grade bonus
- UI: Tuesday-only sidebar widget in 01_live_lines.py (DNP + star-out text inputs)
- Purpose: DraftKings Tuesday KOTC promo — ranks highest projected PRA players.

### calibration.py
- Path: `core/calibration.py`
- Key exports: `get_calibration_report`, `CalibrationReport`, `_brier_score`, `_roc_auc`, `_calibration_bins`
- Gate: MIN_BETS=30 — returns "inactive" report below threshold
- Metrics: Brier score, ROC AUC (Wilcoxon-MWW), calibration bins, ECE approximation
- Purpose: Validates sharp score prediction accuracy once 30+ graded bets accumulated.

### clv_tracker.py
- Path: `core/clv_tracker.py`
- Key exports: `log_clv_snapshot`, `read_clv_log`, `clv_summary`, `print_clv_report`
- Storage: CSV at `logs/clv_log.csv`
- Purpose: Closing Line Value snapshot and summary reporting.

### price_history_store.py
- Path: `core/price_history_store.py`
- DB: `price_history.db` (SQLite)
- Key exports: `init_price_history_db`, `record_open_prices`, `inject_historical_prices_into_cache`, `purge_old_events`, `get_all_open_prices`
- Purpose: Persistent open-price store for multi-session RLM continuity. Auto-purges >14 days.

### probe_logger.py
- Path: `core/probe_logger.py`
- Key exports: `log_probe_result`, `read_probe_log`, `probe_summary`, `probe_log_status`
- Storage: `data/probe_log.json`
- Purpose: Bookmaker availability probe log.

---

## Test Coverage

| Module | Test File | Tests |
|---|---|---|
| math_engine | test_math_engine.py | 217 |
| tennis_data | test_tennis_data.py | 96 |
| king_of_the_court | test_king_of_the_court.py | 74 |
| nba_pdo | test_nba_pdo.py | 66 |
| originator_engine | test_originator_engine.py | 62 |
| injury_data | test_injury_data.py | 59 |
| efficiency_feed | test_efficiency_feed.py | 51 |
| parlay_builder | test_parlay_builder.py | 47 |
| odds_fetcher | test_odds_fetcher.py | 47 |
| clv_tracker | test_clv_tracker.py | 46 |
| calibration | test_calibration.py | 46 |
| probe_logger | test_probe_logger.py | 36 |
| price_history_store | test_price_history_store.py | 36 |
| scheduler | test_scheduler.py | 35 |
| nhl_data | test_nhl_data.py | 34 |
| line_logger | test_line_logger.py | 31 |
| weather_feed | test_weather_feed.py | 24 |
| **Total** | | **1007 / 1007 passing** |

---

## Key Dependencies

- `streamlit` — UI framework (1.36+, `st.navigation` + `st.Page`)
- `APScheduler` — background polling scheduler
- `requests` — Odds API HTTP calls + Open-Meteo weather
- `pandas` — Analysis tab dataframes
- `plotly` — Charts in analysis, R&D, and simulator tabs
- `nba_api` — NBA stats (free, no key — PDO regression signal)
- `sqlite3` — Built-in; WAL mode for concurrent writes
- Python 3.13 (use `datetime.now(timezone.utc)` not `datetime.utcnow()`)

---

## Architecture Rules (Non-Negotiable)

- Package imports: `from core.math_engine import ...` (NOT root-level like V36)
- NEVER import math_engine from odds_fetcher — circular import
- NEVER import other core modules into math_engine — pure math only
- Streamlit: `st.html()` for full HTML slates; `st.markdown(unsafe_allow_html=True)` for global CSS; inline styles in card renderers
- Scheduler: guarded by `st.session_state` to prevent restart on rerun
- SQLite WAL mode active — safe for concurrent scheduler + UI reads
- nba_api: always use `_endpoint_factory` injection pattern — NOT unittest.mock.patch
- Kill switch cache-seeding: seed module cache BEFORE calling kill switch function

## UI Design Tokens

- Brand: `#f59e0b` (amber) | Positive: `#22c55e` | Nuclear: `#ef4444`
- Background: `#0e1117` | Card: `#1a1d23` | Border: `#2d3139`
- Plotly: `paper_bgcolor="#0e1117"`, `plot_bgcolor="#13161d"`, `font.color="#d1d5db"`

## Math Invariants

- Collar: -180 to +150 (soccer expanded: -250 to +400)
- Min edge: 3.5% | Min books for consensus: 2
- Kelly: 0.25x fraction; >60% → 2.0u NUCLEAR, >54% → 1.0u STANDARD, else 0.5u LEAN
- SHARP_THRESHOLD = 45 (raise to 50-55 after RLM fires ≥20 times live)
- NUCLEAR requires ≥90 sharp score. Max base = 85 (edge 40 + RLM 25 + eff 20). Injury boost = up to +5.
- RLM trigger: 3% implied prob shift; passive (cold cache) → active on 2nd fetch

---

## Quick Start

```bash
cd ~/ClaudeCode/agentic-rd-sandbox
streamlit run app.py --server.port 8504
python3 -m pytest tests/ -q
```
