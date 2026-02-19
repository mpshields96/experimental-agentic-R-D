# SESSION_LOG.md — Titanium-Agentic

---

## Session 7 — 2026-02-19

### Objective
Build R&D EXP 1 (CLV Tracker) and R&D EXP 2 (Pinnacle Probe) — both marked
"BUILD NOW" in the ecosystem MASTER_ROADMAP.

### Context Sync
- Read-only survey of titanium-v36 and titanium-experimental completed in Session 6.
- Synced against MASTER_ROADMAP.md (titanium-v36 memory/docs, created Session 20 of v36).
- MASTER_ROADMAP Section 3 (R&D Experimental Backlog):
  - R&D EXP 1: CLV Tracker [BUILD NOW] ← delivered this session
  - R&D EXP 2: Pinnacle Probe [BUILD NOW] ← delivered this session
- sandbox is architecturally ahead of v36 on RLM (DB-seeded cold start) and
  CLV tracking (CSV accumulation). v36 has the live Streamlit Cloud deploy.

### What Was Built

#### 1. `core/odds_fetcher.py` — Pinnacle Probe (R&D EXP 2)
- `probe_bookmakers(raw_games)` — surveys all bookmaker keys in a raw games list
  - Returns: all_keys (sorted), pinnacle_present (bool), preferred_found, n_games_sampled, per_game (first 5)
  - Zero API calls — works on any already-fetched raw_games dict
  - Design: diagnostic only — does NOT modify PREFERRED_BOOKS or any state
- `print_pinnacle_report(probe_result)` — human-readable stdout report for CLI + HANDOFF.md

#### 2. `core/clv_tracker.py` — CLV Tracker (R&D EXP 1)
New file. Persistence layer on top of math_engine.calculate_clv().
- `log_clv_snapshot(event_id, side, open_price, bet_price, close_price)` → appends to CSV
  - CLV stored as percentage (e.g. 1.88, not 0.0188)
  - Grade auto-populated from math_engine.clv_grade()
  - Creates CSV + parent dirs on first call
  - Thread-safe (append mode)
- `read_clv_log(last_n)` → list[dict] with float/int type coercion
- `clv_summary(entries)` → {n, avg_clv_pct, positive_rate, max, min, below_gate, verdict}
  - Gate: 30 entries minimum (CLV_GATE constant)
  - Verdict tiers: STRONG EDGE CAPTURE / MARGINAL / NO EDGE / INSUFFICIENT DATA
- `print_clv_report(log_path)` → stdout report with grade breakdown

#### 3. `pages/04_bet_tracker.py` — CLV wire-in
- On bet grade submit: if close_price provided → `log_clv_snapshot()` fires automatically
- Open price sourced from RLM cache (`get_open_price(event_id, side)`); falls back to bet_price
- Failure isolated: CLV log error never blocks bet result save

#### 4. `tests/test_clv_tracker.py` — 46 new tests
- TestLogClvSnapshot (10 tests): file creation, math accuracy, % vs decimal storage
- TestReadClvLog (7 tests): type coercion, last_n, missing file
- TestClvSummary (12 tests): gate logic, all 4 verdict strings, edge cases
- TestPrintClvReport (3 tests): smoke tests
- TestProbeBookmakers (11 tests): pinnacle detection, dedup, cap, empty games
- TestPrintPinnacleReport (3 tests): smoke tests

**Total: 226/226 tests passing (was 180/180)**

### Architecture Notes
- CLV tracker is a separate file (not stuffed into math_engine) — one file = one job
- CSV path: `data/clv_log.csv` (relative to sandbox root). Override via `CLV_LOG_PATH` env var.
- No circular imports: clv_tracker imports from math_engine only (not odds_fetcher)
- probe_bookmakers is zero-cost (no API calls) — run against any cached fetch

### Wire-in Instructions (future)
When scheduler polls fire: call `probe_bookmakers(raw_games["NBA"])` on any NBA fetch day.
Print or log result. If pinnacle_present=True → evaluate adding to PREFERRED_BOOKS.

### Next Session Recommendation
Session 8 options (from MASTER_ROADMAP):
A. Expose CLV report in pages/05_rd_output.py — live CLV grade distribution chart
B. RLM 2.0: price_history_store.py — SQLite persistent open-price store (multi-day baseline)
   Mirrors experimental Session 18's price_history.json design but SQLite-backed
C. Sharp Score calibration: scatter edge% vs outcome (needs 20+ graded bets first — future)
Priority: B (RLM 2.0) — highest structural value, no gate needed

---

## Session 2 — 2026-02-18/19

### Objective
Build scheduler + Streamlit entry point + Priority 1 (line history tab) + Priority 2 (live lines scaffold).

### What Was Built
- [x] `core/scheduler.py` — APScheduler in-process with st.session_state guard
  - `start_scheduler()`, `stop_scheduler()`, `trigger_poll_now()`, `get_status()`
  - `reset_state()` for test isolation
  - Polls `_poll_all_sports()` every 5 min → `log_snapshot()` per sport
  - Error list capped at 10, error count tracked for UI display
- [x] `tests/test_scheduler.py` — 26 tests passing
- [x] `app.py` — Streamlit entry point
  - `st.navigation()` + `st.Page()` programmatic nav (Streamlit 1.36+)
  - Scheduler init with `st.session_state` guard
  - Sidebar: scheduler status dot, last poll time, "Refresh Now" button, quota display
  - Global CSS injection (global style block via `st.markdown(unsafe_allow_html=True)`)
- [x] `pages/01_live_lines.py` — Full bet-ranking pipeline
  - `_fetch_and_rank()` cached (60s TTL) — fetch + parse + sort by edge%
  - `_bet_card()` renders via `st.html()` with inline styles
  - Filters: sport, market type, min sharp score, auto-refresh toggle
  - Math breakdown expander: shows every calculation step
  - Graceful no-data state
- [x] `pages/03_line_history.py` — Priority 1 (line history display)
  - Status bar: total lines, distinct games, flagged movements, scheduler status
  - `_movement_card()` via `st.html()` — two-column card grid
  - Game drill-down: `_build_sparkline()` Plotly chart + data table
  - RLM open price seed table
  - Graceful empty states throughout
- [x] `pages/02_analysis.py` — Stub (Session 4 target)
- [x] `pages/04_bet_tracker.py` — Stub (Session 3 target)
- [x] `pages/05_rd_output.py` — Stub (Session 5 target)

**Total: 180/180 tests passing**

### UI Design Decisions (Session 2)
- Dark terminal aesthetic: `#0e1117` bg, `#f59e0b` amber brand accent
- `st.html()` for cards; inline styles only in components
- `st.navigation()` + `st.Page()` programmatic navigation
- Plotly dark: `paper_bgcolor="#0e1117"`, `plot_bgcolor="#13161d"`
- WebSearch was not available in subagent — applied production-validated patterns from known Streamlit behavior instead

### Blockers / Notes
- APScheduler was not installed; ran `pip3 install APScheduler`
- `datetime.utcnow()` deprecated in Python 3.13 — replaced with `datetime.now(timezone.utc)` throughout
- `st.navigation()` requires Streamlit 1.36+ — documented in CONTEXT_SUMMARY.md

### Next Session Recommendation
Session 3: Build `pages/04_bet_tracker.py` (Bet Tracker tab)
- Rebuild from bet-tracker logic reference (log bets, outcomes, P&L, CLV per bet)
- Add "Log Bet" button to live_lines page linking to tracker
- Build ROI summary: win rate, avg edge, avg CLV, sport breakdown
- Unit test: `tests/test_bet_tracker_page.py` for any helper functions extracted to core

---

## Session 1 — 2026-02-18

### Objective
Bootstrap the project: git init, context absorption, CONTEXT_SUMMARY.md,
then build and test the three Priority 1 modules: math_engine, odds_fetcher, line_logger.

### What Was Built
- [x] `~/ClaudeCode/agentic-rd-sandbox/` directory structure
- [x] `git init` — clean sandbox
- [x] Plugin/skill audit (see CONTEXT_SUMMARY.md)
- [x] `CONTEXT_SUMMARY.md` — ground truth document
- [x] `SESSION_LOG.md` (this file)
- [x] `core/__init__.py` + `core/data/__init__.py`
- [x] `core/math_engine.py` — 91 tests passing
- [x] `core/odds_fetcher.py` — 32 tests passing
- [x] `core/line_logger.py` + SQLite schema — 31 tests passing
- [x] `tests/test_math_engine.py` — 91 tests
- [x] `tests/test_odds_fetcher.py` — 32 tests
- [x] `tests/test_line_logger.py` — 31 tests
- [x] `requirements.txt`
- [x] `.gitignore`

**Total: 154/154 tests passing**

### Context Absorbed
- Read `~/Projects/titanium-v36/CLAUDE.md` — all non-negotiable rules
- Read `~/Projects/titanium-v36/edge_calculator.py` — full math: Kelly, edge, Sharp Score,
  kill switches, consensus fair prob, `parse_game_markets()`, `calculate_edges()`
- Read `~/Projects/titanium-v36/odds_fetcher.py` (first 100 lines) — API structure,
  QuotaTracker, PREFERRED_BOOKS, MARKETS dict, sport key mapping
- Read `~/Projects/titanium-v36/bet_ranker.py` (first 80 lines) — rank_bets() structure,
  SHARP_THRESHOLD=45, diversity rules
- Read `~/Projects/titanium-experimental/HANDOFF.md` — full R&D session history,
  RLM architecture, std_dev finding (r=+0.020, display-only), injury API (B2 pending),
  efficiency feed design (110 teams: 30 NBA + 80 NCAAB + NHL + MLB planned)
- Read `~/Projects/bet-tracker/CLAUDE.md` — standalone HTML bet tracker reference
  (P&L formula, data model, validation rules)

### Key Architectural Decisions for Session 1
1. `core/math_engine.py` = edge_calculator equivalent + RLM cache + CLV functions
   New vs V36: adds `clv()` function and `cache_line_snapshot()` for active RLM tracking
2. `core/odds_fetcher.py` = direct port of V36 odds_fetcher with package-level imports
   Added: `fetch_batch_odds()` convenience wrapper for the scheduler
3. `core/line_logger.py` = NEW (not in V36) — SQLite persistence for line history
   Schema: see CONTEXT_SUMMARY.md; WAL mode enabled

### Blockers / Open Questions
None at session start.

### Next Session Recommendation
Session 2: Build `core/scheduler.py` + `app.py` + `pages/03_line_history.py`
(the line history tab that makes use of line_logger.db data).
Then build the scaffolding for `pages/01_live_lines.py`.

---
