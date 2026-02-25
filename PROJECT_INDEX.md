# Project Index: Titanium-Agentic Sandbox

Generated: 2026-02-25 (Session 28 wrap) | Tests: 1103/1103 ✅ | Last commit: e294539 (pushed)

**Read this file at session start instead of scanning the full codebase. ~94% token reduction.**
See CLAUDE.md for rules, MASTER_ROADMAP.md for task backlog, SESSION_LOG.md for history.

---

## ⚠️ ACTIVE CRITICAL BUG — READ BEFORE ANY WORK

**parse_game_markets() totals consensus bug** — blocks all live betting on totals.
Live scan showed BOTH Over 7.0 AND Under 6.5 for EDM @ ANA as Grade B simultaneously.
Root cause: `consensus_fair_prob()` mixes books quoting different total lines (6.5 vs 7.0).
V37 hard audit requested (V37_INBOX.md). Fix is Session 29 Priority #1.

---

## 📋 Priority Order (Session 29+)

**#1 — Fix parse_game_markets() totals consensus bug** (see V37_INBOX for audit spec)
**#2 — UI modernisation** (modern Apple/visionOS: 01_live_lines, 04_bet_tracker, 07_analytics)
**#3 — Live run** (only after #1 fixed and validated)

---

## 📁 Directory Structure

```
agentic-rd-sandbox/
├── app.py                   ← Streamlit entry, navigation, scheduler start
├── pages/
│   ├── 00_guide.py          ← System guide / onboarding
│   ├── 01_live_lines.py     ← PRIMARY: live scan, grade tier display, Log Bet
│   ├── 02_analysis.py       ← Manual analysis tools
│   ├── 03_line_history.py   ← Line movement charts
│   ├── 04_bet_tracker.py    ← Manual bet logging + resolution form
│   ├── 05_rd_output.py      ← R&D output / probe logs
│   ├── 06_simulator.py      ← Simulation tools
│   └── 07_analytics.py      ← Analytics dashboard (unlocks at 10 resolved bets)
├── core/
│   ├── math_engine.py       ← ⚠️ PRIMARY MATH — BetCandidate, parse_game_markets, consensus, kill switches
│   ├── odds_fetcher.py      ← Odds API client, quota tracking, batch fetch
│   ├── line_logger.py       ← SQLite: bet_log, line_snapshots, price_history
│   ├── analytics.py         ← Post-facto analytics (Sharp ROI, RLM, CLV, equity)
│   ├── calibration.py       ← Model calibration: Brier, ROC-AUC, edge accuracy
│   ├── scheduler.py         ← APScheduler: 5-min polls, NHL goalies, inactivity guard
│   ├── nba_pdo.py           ← NBA PDO kill switch (shot quality regression)
│   ├── king_of_the_court.py ← KOTC: top PRA candidate picker (Tuesday NBA)
│   ├── injury_data.py       ← Injury kill switch (positional leverage)
│   ├── tennis_data.py       ← Tennis surface inference, kill switch
│   ├── nhl_data.py          ← NHL goalie status (starter confirmation gate)
│   ├── efficiency_feed.py   ← Team efficiency gap (structural edge signal)
│   ├── weather_feed.py      ← NFL wind data (totals kill switch input)
│   ├── clv_tracker.py       ← Closing line value tracking
│   ├── originator_engine.py ← Line originator inference
│   ├── parlay_builder.py    ← Parlay construction
│   ├── price_history_store.py ← Price movement history
│   └── probe_logger.py      ← Book probe logging
├── tests/                   ← 1103 unit tests across 18 files
├── scripts/
│   ├── grade_bet.py         ← CLI: grade a bet manually
│   └── export_bets.py       ← CLI: export bet_log to CSV
├── memory/
│   ├── ORIGINAL_PROMPT.md   ← Session handoff init prompt (update before every new chat)
│   ├── RESUME_PROMPT.md     ← Quick resume template
│   ├── NEW_CHAT_INIT_PROMPT.md
│   └── REVIEWER_PROMPT.md
├── V37_INBOX.md             ← Builder → V37 coordination (V37 reads at startup)
├── REVIEW_LOG.md            ← V37 → Builder findings (builder reads at startup)
├── SESSION_LOG.md           ← Session history
├── MASTER_ROADMAP.md        ← Long-term roadmap
├── CLAUDE.md                ← Rules, access controls, skills mandate
└── data/
    ├── titanium.db          ← SQLite: bet_log, line_snapshots, price_history
    ├── daily_quota.json     ← Odds API daily credit tracking
    └── probe_log.json       ← Book probe data
```

---

## 🚀 Entry Points

```bash
# App (requires ODDS_API_KEY env var)
ODDS_API_KEY=<key> streamlit run app.py --server.port 8504

# Tests
python3 -m pytest tests/ -q   # 1103/1103 expected

# CLI tools
python3 scripts/export_bets.py
python3 scripts/grade_bet.py
```

---

## 📦 Core Modules — Key API

### math_engine.py (249 tests) — THE BRAIN

```python
# Data model
@dataclass BetCandidate:
    sport, matchup, market_type, target, line, price
    edge_pct, win_prob, market_implied, fair_implied
    kelly_size, sharp_score, signal, grade, kill_reason, rlm_confirmed

# Grade pipeline
assign_grade(bet: BetCandidate) -> None  # mutates in-place

# Core pipeline (call once per game dict, not per games list)
parse_game_markets(game: dict, sport: str, ..., min_edge: float) -> list[BetCandidate]

# Consensus (⚠️ BUGGY for totals — mixes different book lines)
consensus_fair_prob(team, market_key, side, bookmakers) -> (prob, std, n_books)

# Kill switches
nba_kill_switch / nfl_kill_switch / ncaab_kill_switch / nhl_kill_switch
soccer_kill_switch / ncaaf_kill_switch / tennis_kill_switch

# Constants
MIN_EDGE = 0.035         GRADE_B_MIN_EDGE = 0.015
GRADE_C_MIN_EDGE = 0.005 NEAR_MISS_MIN_EDGE = -0.01
KELLY_FRACTION = 0.25    KELLY_FRACTION_B = 0.12    KELLY_FRACTION_C = 0.05
SHARP_THRESHOLD = 45     (raise to 50-55: 5 live sessions + 20 RLM fires)
```

### odds_fetcher.py (51 tests)

```python
# IMPORTANT: sports param takes friendly names ("NBA", "NHL"), NOT API keys
fetch_batch_odds(sports: list[str], include_tennis: bool) -> dict[sport_name, list[game_dict]]

# Each game_dict must be passed to parse_game_markets() individually (not the list)
fetch_game_lines(sport_key: str) -> list[dict]

# Credit limits
DAILY_CREDIT_CAP = 300    SESSION_CREDIT_SOFT_LIMIT = 120
SESSION_CREDIT_HARD_STOP = 200    BILLING_RESERVE = 150

# ACTIVE_SPORTS excludes MLB (on hold until Apr 1, 2026)
ACTIVE_SPORTS = ["NBA","NFL","NCAAF","NCAAB","NHL","EPL","LIGUE1","BUNDESLIGA","SERIE_A","LA_LIGA","MLS"]
```

### line_logger.py (35 tests)

```python
log_bet(sport, matchup, market_type, target, price, edge_pct, kelly_size,
        stake, notes, sharp_score, rlm_fired, tags, book, days_to_game, line, signal,
        grade: str = "", db_path=None) -> int

get_bets(db_path) -> list[dict]          # all logged bets
update_bet_result(bet_id, result, ...)   # resolve a bet
init_db(db_path)                         # idempotent schema + migrations
# bet_log columns include: grade, sharp_score, signal, rlm_fired, clv, days_to_game, line
```

### analytics.py (51 tests) — LOCKED: need 10 resolved bets (have 4 logged, 0 resolved)

```python
MIN_RESOLVED = 10   # was 30, lowered Session 27
compute_sharp_roi_correlation / compute_rlm_correlation / compute_clv_beat_rate
compute_equity_curve / compute_rolling_metrics / compute_book_breakdown
```

### calibration.py (46 tests) — LOCKED: need 10 bets

```python
MIN_BETS_FOR_CALIBRATION = 10   # was 30, lowered Session 27
get_calibration_report(db_path) -> CalibrationReport  # Brier, ROC-AUC, edge accuracy
```

---

## 🛡️ Kill Switch Coverage

| Sport | Module | Key Signals |
|-------|--------|-------------|
| NBA | math_engine + nba_pdo | B2B, spread >14, PDO regression |
| NFL | math_engine + weather_feed | Wind >20mph hard kill, FORCE_UNDER |
| NCAAB | math_engine | Pace std_dev, totals volatility |
| NHL | math_engine + nhl_data | Unconfirmed goalie, collar |
| Soccer | math_engine | Poisson cross-validation |
| NCAAF | math_engine | Conference mismatch, spread extremes |
| Tennis | math_engine + tennis_data | Surface mismatch, ranking gap |
| Injury | injury_data | Positional leverage (QB, PG, etc.) |

---

## 🏗️ Grade Tier System

| Grade | Edge | Kelly | Stake |
|-------|------|-------|-------|
| A | ≥ 3.5% | 0.25× | Full (STANDARD/NUCLEAR tier) |
| B | ≥ 1.5% | 0.12× | $50 max |
| C | ≥ 0.5% | 0.05× | $0 tracking only |
| NEAR_MISS | ≥ -1.0% | 0 | Display only |

---

## 🔗 Two-AI Coordination

| File | Direction | Auto-read? |
|------|-----------|-----------|
| V37_INBOX.md | Builder → V37 | V37 reads at every startup |
| REVIEW_LOG.md | V37 → Builder | Builder reads at every startup |
| memory/ORIGINAL_PROMPT.md | Builder → Next session | Paste as new chat opener |

---

## 📊 Test Counts by Module

| Module | Tests | Module | Tests |
|--------|-------|--------|-------|
| math_engine | 249 | calibration | 46 |
| tennis_data | 96 | scheduler | 40 |
| king_of_the_court | 74 | probe_logger | 36 |
| nba_pdo | 66 | price_history_store | 36 |
| originator_engine | 62 | line_logger | 35 |
| injury_data | 59 | nhl_data | 34 |
| odds_fetcher | 51 | weather_feed | 24 |
| efficiency_feed | 51 | | |
| analytics | 51 | **TOTAL** | **1103** |
| parlay_builder | 47 | | |
| clv_tracker | 46 | | |

---

## 🎨 UI Design System (Session 27 permanent directive)

Aesthetic: modern Apple / visionOS / macOS Sequoia — NOT old skeuomorphic
- Translucent layers, clean geometry, generous whitespace, precise typography
- Font: IBM Plex Mono (code/numbers) + IBM Plex Sans (text)
- Brand: `#f59e0b` amber | Positive: `#22c55e` | Nuclear: `#ef4444`
- Background: `#0e1117` | Card: `#1a1d23` | Border: `#2d3139`
- Plotly: `paper_bgcolor="#0e1117"`, `plot_bgcolor="#13161d"`
- Interactions: instant, frictionless — no spinner fatigue, no nav confusion
- **`frontend-design:frontend-design` skill MANDATORY for all UI work**

---

## 🔑 Architecture Notes

- Package imports: `from core.math_engine import` (NOT root-level like V36)
- SQLite WAL mode enabled — safe for scheduler concurrent writes
- Streamlit: `st.html()` for full HTML slates (NOT `st.markdown()`)
- `st.navigation()` + `st.Page()` programmatic nav (Streamlit 1.36+)
- NEVER import math_engine from odds_fetcher — circular import risk
- nba_api: use `_endpoint_factory` injection — NOT `unittest.mock.patch`
- "LA Clippers" normalization: nba_api returns "LA Clippers" not "Los Angeles Clippers"
- Kill switch cache-seeding: seed module cache BEFORE calling pdo_kill_switch()
- Edge test fixture: tight spread prices (-108/-112) don't generate >3.5% edge — use outlier-book pattern
- fetch_batch_odds() returns dict by friendly name; parse_game_markets() takes ONE game dict, not the list
