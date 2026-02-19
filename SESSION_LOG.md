# SESSION_LOG.md — Titanium-Agentic

---

## Session 12 — 2026-02-19

### Objective
Sports coverage audit + kill switch coverage map. Verify system tracks user's
requested sport list. Enforce "follow your recommendations" posture:
no speculative additions, Math > Narrative, hold anything without tier confirmation.

### Sports Coverage Audit Results

#### Requested vs Configured
| Sport | System Key | API Key | Kill Switch | Status |
|---|---|---|---|---|
| NBA | NBA | basketball_nba | ✅ B2B rest + pace variance | Active |
| NCAAB | NCAAB | basketball_ncaab | ✅ 3PT reliance + tempo | Active |
| NCAAF | NCAAF | americanfootball_ncaaf | ⚠️ None (collar-only) | Active |
| NFL | NFL | americanfootball_nfl | ✅ Wind + backup QB | Active |
| EPL | EPL | soccer_epl | ✅ Market drift + dead rubber | Active |
| Ligue 1 | LIGUE1 | soccer_france_ligue_one | ✅ Same soccer kill | Active |
| Bundesliga | BUNDESLIGA | soccer_germany_bundesliga | ✅ Same soccer kill | Active |
| Serie A | SERIE_A | soccer_italy_serie_a | ✅ Same soccer kill | Active |
| La Liga | LA_LIGA | soccer_spain_la_liga | ✅ Same soccer kill | Active |
| MLS | MLS | soccer_usa_mls | ✅ Same soccer kill | Active |
| NHL | NHL | icehockey_nhl | ⚠️ None (collar-only) | Active |
| MLB | MLB | baseball_mlb | ⚠️ None (collar-only) | Active, season Mar 27 |
| Tennis | — | — | ❌ Not configured | **DEFERRED** |
| College Baseball | — | — | ❌ Not configured | **DEFERRED** |

#### Soccer spreads note
Spreads excluded from all soccer markets by design. Odds API returns 422 on
soccer spread requests via bulk endpoint — h2h and totals only. Confirmed Feb 2026.

#### Kill Switch Gaps (NCAAF, NHL, MLB)
These three sports are active and polling correctly. They run on:
- Collar check (-180 to +150)
- MIN_EDGE (3.5%)
- SHARP_THRESHOLD (45)
- Full Sharp Score composite (edge + RLM + efficiency + situational)
- Consensus fair probability across books

That is meaningful protection. The collar alone eliminates most bad price markets.
No sport-specific kill needed until live data identifies a real recurring problem:

**NCAAF**: NFL kill switch is applicable in bowl season (wind/backup QB), but
NCAAF-specific kill would need: SOS differentiation, non-con blowout bias,
or late-line movement patterns. Deferred — no validated threshold yet.

**NHL**: Goalie injury (confirmed starter scratched) is the main kill candidate.
No real-time goalie confirmation API available without paid feed. Deferred.

**MLB**: Pitcher fatigue (days rest, pitch count from prior start) + weather
(wind out/in at Wrigley-type parks). API data insufficient until season starts.
Deferred — revisit April 2026 after 2+ weeks of live MLB data.

#### Deferred Sports (Tennis, College Baseball)
**Tennis**: Odds API supports tennis_atp and tennis_wta. Two constraints:
1. Kill switch: Surface type (clay/hard/grass) + H2H are the validated inputs.
   Neither is available from Odds API — requires separate data source.
2. Quota: +2 sports = 14 API calls per 5-min poll. Tier must support it.
Action: Add only after user confirms API tier covers tennis AND supply of
surface/H2H data. Do not add as collar-only — tennis volatility is too high.

**College Baseball**: Sparse line posting (1-2 days before game only), thin
sharp movement data, no pitcher injury feed available from Odds API.
Action: Deferred indefinitely. Low ROI vs quota cost.

### Origination Method — Confirmed Deferred
Recommendation confirmed: do NOT implement Pinnacle-anchored true origination
until `probe_log.json` shows `pinnacle_present: True` consistently (3+ consecutive
poll sessions). Current state: Pinnacle ABSENT on this API tier.
`price_history_store.py` continues as session-relative proxy open price — valid
for RLM detection within session. CLV via `clv_tracker.py` is retroactive
verification of that proxy. Structurally sound, no false confidence.

### Data Source Research (Session 12)

Research conducted on available free APIs for deferred kill switches:

#### NHL Goalie API — ✅ VIABLE (FREE) — ENDPOINT STRUCTURE CONFIRMED
- `api-web.nhle.com/v1/gamecenter/{gameId}/boxscore` — confirmed working, public, no key
- Field: `playerByGameStats.awayTeam.goalies[n].starter` (bool) — CONFIRMED
- **CORRECTION**: Schedule endpoint does NOT have `startingGoalies` for future games.
  Starter only populates in boxscore when game moves from FUT → loading state (T-60min).
- Strategy: poll boxscore at T-60min intervals in scheduler until starter appears
- **Zero quota cost** — completely independent of Odds API
- **Status: READY TO BUILD** — no more verification needed

#### MLB Starting Pitcher API — ✅ VERIFIED (FREE, season-gated)
- `statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,team`
- **CONFIRMED field**: `games[].teams.home.probablePitcher.fullName` and `.id`
- Days rest: `people/{id}?hydrate=stats(group=pitching,type=gameLog)` →
  `stats[0].splits[].stat.numberOfPitches` + `date` (confirmed live for multiple pitchers)
- TBD pitcher = null probablePitcher field = FLAG condition
- **Deferred to Apr 1 2026** — season starts Mar 27, thresholds need live validation
- Friction point: MLB full team names vs Odds API abbreviated names — need lookup table

#### Tennis ATP/WTA — ✅ ON ODDS API (tier TBD), ⚠️ SURFACE DATA = $40/mo
- The Odds API: tennis_atp / tennis_wta likely require paid "All Sports" tier (unconfirmed)
- Surface + H2H data: **api-tennis.com confirmed** — has clay/hard/grass W/L splits per player
  per season, H2H records, fixture data. Starter plan $40/mo (14-day free trial available)
- Decision: HOLD tennis until user approves api-tennis.com cost + Odds API tier confirmed
- Surface type is inferred from tournament name (not a direct field) — needs lookup table

#### College Baseball — ❌ REJECTED (confirmed dead end)
- MLB Stats API covers college baseball at sportId=22 — confirmed
- **BUT**: `probablePitcher` is NOT populated for college games (field absent, not null)
- Thin bookmaker coverage (2-3 books max), no sharp action, line posting sparse
- **Verdict: Do not add to system at all. No viable path to a meaningful kill switch.**

### What Was Built This Session
- **MASTER_ROADMAP.md** — created + updated with verified API research:
  exact endpoint specs, confirmed field names, corrected NHL/MLB assumptions,
  tennis cost confirmed ($40/mo api-tennis.com), college baseball rejected
- **PROJECT_INDEX.md** — created: full codebase map in ~3K tokens
  (replaces reading 58K+ tokens of source). Covers all public APIs,
  import rules, test counts, data files, design system, system gates
- **CLAUDE.md** — complete rewrite: master init prompt for new chat.
  Full role definition, prohibited paths (titanium-v36/experimental = read-only),
  session start/end rituals, math non-negotiables, current state, Session 13 directive
- **CONTEXT_SUMMARY.md** — updated to Session 12: full arch state, build diary,
  complete capability map vs V36, kill switch table, session history table
- No code changes — documentation + research session. Math is sound.
- 314/314 tests passing (unchanged)

### Next Session Recommendations (Session 13)
See MASTER_ROADMAP.md Section 9 for full checklist. Summary:

**API research complete. W1 and W2 are resolved. Ready to build.**

**PRIORITY:**
1. Build `core/nhl_data.py` — NHL boxscore poller, team name normalizer, starter detection
   Endpoint confirmed: `api-web.nhle.com/v1/gamecenter/{gameId}/boxscore`
   Field confirmed: `playerByGameStats.{team}.goalies[n].starter` (bool)
2. Add `nhl_kill_switch()` to math_engine.py + tests
3. Wire NHL kill into scheduler._poll_all_sports() NHL branch

**CAN DO ON ANY WIFI:**
4. Check bet tracker graded count — if ≥10, build CLV vs edge% scatter (Analysis ③)
5. Check RLM gate sidebar — if RAISE READY, manually raise SHARP_THRESHOLD to 50

**PERMANENT HOLDS:**
- Tennis: until user approves api-tennis.com $40/mo + confirms Odds API tier
- MLB kill: Apr 1 gate — season hasn't started
- Origination: until Pinnacle confirmed present in probe log
- College Baseball: REJECTED — do not add

---

## Session 11 — 2026-02-19

### Objective
RLM fire gate counter — accumulate confirmed RLM detections toward
SHARP_THRESHOLD raise (45→50). DB path bug fix. Sports audit.

### What Was Built

#### 1. `core/math_engine.py` — RLM fire counter
- New module-level state: `_rlm_fire_count: int = 0`
- New constant: `RLM_FIRE_GATE: int = 20` — target fires before threshold raise
- `compute_rlm()` now increments `_rlm_fire_count` each time it returns `True`
- New public functions:
  - `get_rlm_fire_count() -> int` — current cumulative count
  - `reset_rlm_fire_count() -> None` — testing only
  - `rlm_gate_status() -> dict` — structured gate state:
    `{fire_count, gate, pct_to_gate, gate_reached}`

#### 2. `core/scheduler.py` — RLM gate in get_status()
- Added import: `rlm_gate_status` from `core.math_engine`
- `get_status()` now returns `"rlm_gate": rlm_gate_status()` — UI reads from here
- Note: importing math_engine from scheduler is safe (math_engine has no scheduler import)

#### 3. `app.py` — RLM Gate sidebar card + DB path fix
- **Bug fix**: Price History card was reading `line_history.db` — corrected to
  `price_history.db` (separate DB as designed in Session 8)
- New **📈 RLM GATE** sidebar card:
  - Fire count + gate target
  - Amber progress bar (fill = fires / RLM_FIRE_GATE)
  - Green "RAISE READY" badge + call-to-action line when gate_reached=True
  - Stays grey/amber until gate hit — no premature threshold raise noise

#### 4. `tests/test_math_engine.py` — 12 new tests (TestRLMFireCounter)
- Initial state, increment on fire, accumulation, cold-cache no-fire,
  drift-below-threshold no-fire, public_on_side=False no-fire,
  reset zeroes counter, gate status structure, initial gate values,
  gate_reached at threshold, pct capped at 1.0, constant type check
- `TestRLM.setup_method` now also calls `reset_rlm_fire_count()` for isolation

#### 5. `tests/test_scheduler.py` — 1 test updated
- `test_initial_state`: added assertions for `rlm_gate` key + structure

**Total: 314/314 tests passing (was 302/302)**

### Architecture Notes
- RLM fire count is **in-memory only** (resets on process restart). This is
  intentional: it counts confirmed fires in live scheduler polls, not historical
  ones. One process restart = fresh accumulation toward the gate.
- `RLM_FIRE_GATE = 20` is conservative. With 5-min polls, 20 genuine RLM
  detections across multiple sports represents meaningful statistical confidence.
- The gate is advisory only — SHARP_THRESHOLD is still a constant in math_engine.py
  that must be manually changed when gate_reached=True. The sidebar just tells
  you when to act, it doesn't act itself. Math > automation here.

### Next Session Recommendation
Session 12 options:
A. Sports audit + kill switch review — verify each sport's kill switch logic
   against current research (see sports audit question from user)
B. CLV vs edge% scatter in Analysis page — needs 10+ graded bets
C. Manual SHARP_THRESHOLD raise to 50 once RLM gate is reached in live use
Priority: A — user explicitly asked for a sports math audit this session.
          Deliver that as a separate analysis (not code changes unless warranted).

---

## Session 10 — 2026-02-19

### Objective
Sidebar health dashboard — surface real-time system health (Pinnacle probe,
price history, CLV tracker) directly in the app sidebar. Weekly automatic
purge of stale price history rows wired into scheduler.

### What Was Built

#### 1. `app.py` — SYSTEM HEALTH sidebar section
Three new status cards below the quota display, each wrapped in try/except
(ImportError-safe, graceful empty states):

**📡 PINNACLE PROBE card**
- Reads `probe_log_status()` + `probe_summary()` from `core/probe_logger`
- Displays: probes logged, pinnacle rate (%), books seen (up to 4 + overflow count)
- Status badge: ACTIVE (green) or ABSENT (red) based on `pinnacle_present`

**📦 PRICE HISTORY card**
- Reads `price_history_status()` from `core/price_history_store`
- Displays raw status line (N events, M sides)
- Status badge: EMPTY (grey) or OK (green)

**📐 CLV TRACKER card**
- Reads `clv_summary()` from `core/clv_tracker`
- Displays: graded N / GATE, avg CLV%, positive rate
- Status badge: first word of verdict (STRONG / MARGINAL / NO / INSUFFICIENT)
- Amber gate-progress bar (fill = n_graded / CLV_GATE) for visual accumulation cue
- All conditional fields hidden when n=0 (no math on empty data)

Design: inline HTML cards, amber accent, same visual language as scheduler card.
All three cards degrade silently on ImportError — zero crash risk on startup.

#### 2. `core/scheduler.py` — Weekly purge job (10C)
- Added import: `purge_old_events` from `core.price_history_store`
- New internal function: `_purge_old_price_history(db_path, days_old=14)`
  - Calls `purge_old_events(days_old=14)`, logs deleted count
  - Errors logged but never raised (same resilience pattern as poll errors)
- New APScheduler job: `id="weekly_purge"`, trigger=interval, weeks=1
  - Registered in `start_scheduler()` alongside `line_poll`
  - kwargs pass db_path through (same override pattern as line_poll)

#### 3. `tests/test_scheduler.py` — 4 new tests (TestPurgeOldPriceHistory)
- `test_purge_job_registered`: weekly_purge id in add_job call_args_list
- `test_purge_job_has_weekly_interval`: weeks=1 confirmed
- `test_purge_deletes_old_rows`: purge_old_events called with correct args
- `test_purge_error_does_not_raise`: RuntimeError swallowed silently
- Fixed 2 existing tests: `test_adds_line_poll_job` + `test_custom_poll_interval`
  now use `call_args_list[0]` (first add_job call = line_poll) instead of
  `call_args` (last call = weekly_purge after adding second job)

**Total: 302/302 tests passing (was 298/298)**

### Architecture Notes
- Sidebar uses `read_probe_log()` / `probe_summary()` calls directly (not
  `probe_log_status()` string) to get structured data for card rendering.
  `probe_log_status()` is still the right tool for logs/CLI; cards need raw dict.
- `price_history_status()` default path resolves to `data/price_history.db`.
  In app.py, we pass `ROOT / "data" / "line_history.db"` explicitly because
  the RLM 2.0 wire-in uses the main line_history DB path, not a separate file.
  Wait — actually price_history uses its own separate DB. The explicit path
  override matches the scheduler's db_path, not price_history's default.
  TODO: verify this path matches in next live run session.
- Weekly purge: 14-day window removes only stale events. Active season events
  are written every 5 min poll — they're always < 14 days. Safe to run weekly.

### Next Session Recommendation
Session 11 options:
A. SHARP_THRESHOLD raise gate counter: sidebar counter showing live RLM fires.
   Once sufficient live sessions accumulate (target: 5+), consider raising
   SHARP_THRESHOLD from 45 → 50 in math_engine.py.
B. Session continuation: verify sidebar health cards display correctly against
   live data (after price_history_status DB path is confirmed correct).
C. CLV vs edge% scatter (Analysis page, Panel ③): add a new chart once 10+
   graded bets exist with both edge% and CLV populated.
Priority: A (when live RLM fires accumulate) or B (immediate validation check).

---

## Session 9 — 2026-02-19

### Objective
Probe log integration — scheduler logs bookmaker coverage on every poll,
surfaces automatically in R&D Output page (no manual CLI required).

### What Was Built

#### 1. `core/probe_logger.py` — Probe Log (new file)
Persistent JSON log of bookmaker probe results from scheduler polls.

Public API:
- `log_probe_result(probe_result, sport)` → appends entry to probe_log.json
  - Stores: timestamp, sport, n_games_sampled, pinnacle_present, all_keys,
    preferred_found, n_books
  - Rolling trim at 200 entries — prevents unbounded file growth
- `read_probe_log(last_n, sport)` → list[dict], sport filter, missing=[]
- `probe_summary(entries)` → {n_probes, pinnacle_rate, pinnacle_present,
  all_books_seen, preferred_coverage, sports_probed, last_seen}
- `probe_log_status()` → one-line status string for logging/sidebar

Design: JSON (not SQLite) — probe data is tiny + sequential, readable in repo.

#### 2. `core/scheduler.py` — Probe wire-in
- Imports: `probe_bookmakers` from odds_fetcher, `log_probe_result` from probe_logger
- In `_poll_all_sports()`: after `log_snapshot()`, calls:
  `probe_result = probe_bookmakers(games)`
  `log_probe_result(probe_result, sport=sport)`
- Zero extra API calls — probe_bookmakers() works on the already-fetched raw_games

#### 3. `pages/05_rd_output.py` — Pinnacle Probe panel (⑦)
Live panel reading from `data/probe_log.json`:
- KPI strip: Probes, Pinnacle YES/NO, Pinnacle Rate, Books Seen
- Empty state: explains what fires the log, what Pinnacle means
- "Book Coverage" tab:
  - Bar chart: preferred books × times seen across probes
  - All-books-ever-seen tag line
  - Verdict card: PINNACLE AVAILABLE or ABSENT with action guidance
- "Probe History" tab:
  - Scatter/line: n_books per probe (green=pinnacle present, red=absent)
  - Last probe timestamp + sports probed footer

#### 4. `tests/test_probe_logger.py` — 36 new tests
- TestLogProbeResult (12): file creation, fields, pinnacle, rolling trim, parent dirs
- TestReadProbeLog (8): read-back, last_n, sport filter, corrupt file
- TestProbeSummary (11): empty, counts, pinnacle rate, book union, preferred coverage
- TestProbeLogStatus (5): status string format, truncation

**Total: 298/298 tests passing (was 262/262)**

### Architecture Notes
- JSON format chosen over SQLite: probe results are small, sequential writes
  and human-readable for repo debugging. No concurrent write risk (scheduler only).
- probe_logger has NO imports from odds_fetcher — clean separation of concerns.
  Scheduler is the only caller that bridges the two.
- Probe runs per-sport per-poll: accumulates data across all active sports,
  allowing sport-level Pinnacle presence analysis over time.

### Next Session Recommendation
Session 10 options:
A. SHARP_THRESHOLD raise gate UI: sidebar counter showing live RLM fires,
   auto-increment when compute_rlm() returns True on a real fetch
B. app.py sidebar: expose probe_log_status() + price_history_status() + clv_summary()
   in the existing sidebar status section (currently only shows scheduler + quota)
C. Price history purge: add weekly purge_old_events() call to scheduler
   (currently purge exists but is never called automatically)
Priority: B — highest user value with lowest risk. Sidebar already exists in app.py,
          adding 3 status lines is safe and provides real-time health visibility.

---

## Session 8 — 2026-02-19

### Objective
RLM 2.0: persistent open-price store (fixes cold-start problem across restarts).
CLV chart exposed in R&D Output page. Tests for all new modules.

### What Was Built

#### 1. `core/price_history_store.py` — RLM 2.0 (new file)
SQLite-backed append-only store for first-ever-seen market prices across sessions.

Core invariant: `INSERT OR IGNORE` — open price is **never** overwritten.

Public API:
- `init_price_history_db(db_path)` — schema init, separate from line_history.db
- `record_open_prices(event_id, sides, sport)` → n rows inserted (0 if all existed)
- `integrate_with_session_cache(raw_games, sport)` — scan games, persist new events
- `get_historical_open_price(event_id, side)` → int|None
- `inject_historical_prices_into_cache(raw_games)` — seeds math_engine RLM cache from DB
- `purge_old_events(days_old=14)` → rows deleted (housekeeping)
- `price_history_status()` → one-line status string
- `get_all_open_prices(sport)` → nested dict {event_id: {side: price}}

Wire-in sequence (called by scheduler each poll cycle, per sport):
```
integrate_with_session_cache(games, sport)     # Step 1: persist new events
inject_historical_prices_into_cache(games)     # Step 2: seed in-memory cache
log_snapshot(games, sport, db)                 # Step 3: existing call unchanged
```

#### 2. `core/scheduler.py` — RLM 2.0 wire-in
- `init_price_history_db(db_path)` called in `start_scheduler()` alongside `init_db()`
- `integrate_with_session_cache()` + `inject_historical_prices_into_cache()` called
  in `_poll_all_sports()` per sport, before `log_snapshot()`

#### 3. `pages/05_rd_output.py` — CLV Tracker panel (⑥)
Live panel reading from `data/clv_log.csv`:
- KPI strip: Entries, Avg CLV%, Positive Rate, Max, Verdict
- Empty state: instructions for first use
- "Grade Distribution" tab: bar chart EXCELLENT/GOOD/NEUTRAL/POOR + gate progress bar
- "CLV History" tab: scatter+line of last 50 entries, colour-coded, avg hline

#### 4. `tests/test_price_history_store.py` — 36 new tests
- TestInitPriceHistoryDb (3): file creation, idempotent, mkdir
- TestRecordOpenPrices (6): insert, never-overwrite, partial, empty
- TestIntegrateWithSessionCache (7): new games, dedup, empty, no-id, sport tag
- TestGetHistoricalOpenPrice (5): retrieval, miss, negative/positive odds
- TestInjectHistoricalPricesIntoCache (5): seeds cache, doesn't overwrite, empty
- TestPurgeOldEvents (3): zero fresh, purge old, preserve fresh
- TestPriceHistoryStatus (3): empty, counts, multi-event
- TestGetAllOpenPrices (4): nested dict, sport filter, empty, multiple

#### 5. `tests/test_scheduler.py` — fix
- `test_stores_db_path`: added `patch("core.scheduler.init_price_history_db")` so
  the test (which patches init_db) doesn't hit a read-only filesystem path

**Total: 262/262 tests passing (was 226/226)**

### Architecture Notes
- `price_history.db` is a SEPARATE file from `line_history.db` — different write patterns
  (append-only vs upsert). Kept separate by design.
- DB path overridable via `PRICE_HISTORY_DB_PATH` env var (test isolation)
- No circular imports: price_history_store imports math_engine only (for seed call)
- RLM cold-start problem: SOLVED. On process restart, `inject_historical_prices_into_cache()`
  loads multi-day baselines into memory before first fetch runs.

### Next Session Recommendation
Session 9 options:
A. R&D Output page: add Pinnacle probe section — live probe trigger + bookmaker coverage chart
B. Scheduler probe integration: call `probe_bookmakers()` + log result to a probe_log.json
C. SHARP_THRESHOLD raise gate tracker: UI counter in sidebar, increment when RLM fires live
Priority: B — closes the loop between probe_bookmakers() (built S7) and actual scheduler runs.
          Surfaces Pinnacle data automatically without manual CLI runs.

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
