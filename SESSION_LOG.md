# SESSION_LOG.md — Titanium-Agentic

---

## Session 31 — 2026-02-25

### Objective
Streamlit Cloud deploy + startup bug fixes + user UX feedback review + savepoint.

### What shipped
- **Streamlit Cloud live**: `titaniumv37agentic.streamlit.app` — first live deployment of sandbox UI
- **`app.py` — `_init_dbs()`**: Added unconditional DB schema init before scheduler.
  Fixes `sqlite3.OperationalError` on fresh Streamlit Cloud deploy (tables didn't exist).
- **`core/scheduler.py`** — Fixed `init_price_history_db(db_path)` bug: was passing
  `line_history.db` path to price_history init. Now calls no-arg default (price_history.db).
- **`core/odds_fetcher.py`** — V37-flagged docstring cleanup: replaced `(1,000)/(500)/(1,000)`
  with constant name references (`DAILY_CREDIT_CAP`, `SESSION_CREDIT_HARD_STOP`, `BILLING_RESERVE`).

### Tests
1079 → 1079 (no new tests — doc + bug fixes only). All passing ✅

### User feedback logged (see task backlog below)

**Commits:** `19927bd` (DB init fix + scheduler path + docstring), `7c17acc` (V37 inbox update) — PUSHED ✅

---

### SESSION 31 — Task Backlog (user feedback 2026-02-25)

**Priority 1 — Session 32 (next session):**
- [ ] **Agentic workflow**: Claude-in-the-loop betting advisory. I read live candidates via
  SQLite MCP, surface recommendations in chat, user approves/skips, I log via log_bet().
  Actual bet placement always manual. Covers: scan → recommend → approve → log → resolve.
  Guide page Steps 1-7 should describe this hybrid flow.
- [ ] **Game start times**: Add CST-converted commence_time to bet cards in `01_live_lines.py`.
  `commence_time` is already in `BetCandidate` — just not rendered. Convert UTC → CST on display.
- [ ] **Pinnacle probe widget**: Always ABSENT for US markets (Pinnacle doesn't accept US customers,
  not on Odds API US tier). Remove or replace with something useful (book coverage count, books live).
- [ ] **Collar map legend overlap**: R&D output page — legends overlapping on the collar map.
  CSS/layout bug. Fix positioning.

**Priority 2 — Session 32-33:**
- [ ] **Player props — zero-cost path**: Second free Odds API account (500 credits/month) dedicated
  to props only. Called on-demand (not every poll) when Claude flags a game worth checking.
  Also evaluate ActionNetwork unofficial API as props scraper layer.
- [ ] **Guide page update**: Rewrite Steps 1-7 to reflect the new agentic workflow (Claude does
  steps 1-6, user approves at key gates, step 7 = bet placement manual at sportsbook).

**Priority 3 — Future (no date):**
- [ ] **Simulator ELI5 guide**: Add a plain-language helper/tooltip guide to the simulator page.
  User unfamiliar with how to use it. "What does this do?", worked example, parameter descriptions.
- [ ] **Louisiana sportsbooks note**: Current PREFERRED_BOOKS already covers all LA-legal books
  (DK, FD, BetMGM, BetRivers, Caesars). No change needed. Consider adding a "LA-available" badge
  or filter in future UI pass.

**Confirmed not needed:**
- Odds API replacement: already best value for single subscription
- Louisiana books: current list is correct (all five operate in LA)

---

## Session 30 — 2026-02-25

### Objective
Session end ritual for Session 29 + MCP/tooling coordination with V37 + PRECONDITION docstrings
+ UI modernisation (Apple/visionOS aesthetic) for pages 01, 04, 07.

### What Was Built

**Session 29 wrap-up (this session)**
- Session end ritual completed: `claude-md-management`, SESSION_LOG, ORIGINAL_PROMPT, git push
- Commit ca4e3fe (wrap-up), 9c96780 (final hash) pushed successfully

**MCP/Tooling coordination (this session)**
- 4-item proposal evaluated: GitHub MCP (❌ already plugin + security CVE), SQLite MCP (✅ install),
  Sequential Thinking MCP (❌ skip → use docstrings), OddsPapi (⏳ defer, 30 bet gate)
- V37 agreed on all 4 items (REVIEW_LOG.md — Reviewer Session 7)
- `mcp-server-sqlite` installed via pip3: `/Library/Frameworks/Python.framework/Versions/3.13/bin/mcp-server-sqlite`
- `.mcp.json` written to sandbox root — project-scoped MCP
- CLAUDE.md SQLite MCP safety rule added (permanent: write_query/create_table PROHIBITED on titanium.db)

**PRECONDITION docstrings (this session) — Commit 70bd822**
- `consensus_fair_prob()` — totals scoping + API format PRECONDITION
- `_best_price_for()` — canonical-line PRECONDITION for totals
- `compute_rlm()` — direction consistency PRECONDITION + COLD CACHE + POSTCONDITION
- `_canonical_totals_books()` — full CONTRACT block with edge cases
- `parse_game_markets()` — INVARIANTS block (3 invariants)
- All documentation-only. 1079/1079 tests unchanged.

**UI Modernisation — visionOS/macOS Sequoia aesthetic (this session)**

`pages/01_live_lines.py`:
- Stats row: 6× `st.metric()` → custom HTML tile grid (color-coded per grade)
- Grade banners (B/C/Near Miss): pill-style inline labels — label | divider | description
- Parlay header: `PARLAY COMBOS` monospace label + fade divider
- `_parlay_card()`: gradient bg, box-shadow, IBM Plex fonts, rounded stats tiles
- Dividers: `st.markdown("---")` → 1px `rgba(255,255,255,0.05)` HTML divider

`pages/04_bet_tracker.py`:
- Global CSS injection (IBM Plex fonts)
- Title: clean HTML header + subtitle
- P&L summary: 5× `st.metric()` → color-coded stat tiles (win rate/ROI/CLV)
- `_bet_card()`: gradient bg, box-shadow, grade pills, 4-tile layout, timestamp in header
- Subheadings: `st.subheader()` → IBM Plex Sans HTML
- Analytics metadata section: styled Mono divider label
- Footer totals: refined `rgba` flex bar

`pages/07_analytics.py`:
- CSS overhaul: kpi-card, chart-card, sample-guard → gradient bg + `rgba` borders + box-shadow
- Page header: IBM Plex Sans 1.55rem (matches page 01/04)
- Section headers: tighter sizing, darker label color
- Comparison bars: rounded + gradient RLM fill
- Lift badges: added border
- All CLV/divider colors: upgraded to `rgba` system

### Tests
- 1079/1079 ✅ all sessions (UI-only changes, no math touched)

### V37 Coordination
- V37_INBOX.md: Session 30-C added — UI review request (visual spot-check only)
- REVIEW_LOG.md: no new entries needed — UI is sandbox domain

### Commit
- Pending (this session) — pages/01, 04, 07 + V37_INBOX + SESSION_LOG

---

## Session 29 — 2026-02-25

### Objective
Full math audit of core/math_engine.py. Fix parse_game_markets() totals consensus bug (contradictory
simultaneous Over+Under edge). Fix RLM direction bug (abs() → signed drift). Remove 241 lines of dead
narrative code (run_nemesis, calculate_edge, Poisson precompute). Session end wrap-up + push.

### What Was Built / Fixed
- **core/math_engine.py** — _canonical_totals_books() helper: finds modal total line via Counter,
  scopes both consensus_fair_prob() and _best_price_for() to same line set. Eliminates cross-line
  false edge — mathematically impossible to have simultaneous positive edge on both sides after fix.
- **core/math_engine.py** — RLM direction fix: `drift = current_prob - open_prob` (signed). Positive
  = price sharpened (smart money). Negative = price lengthened (public). abs() was causing false RLM
  on BOTH directions — now correctly identifies only smart-money line movement.
- **core/math_engine.py** — Dead code removed: run_nemesis() (241 lines + 5 narrative constants),
  calculate_edge() (outer wrapper with no callers), dead Poisson precompute block.
- **tests/test_math_engine.py** — +7 regression tests (TestTotalsCanonicalLineFix ×4,
  TestRLMDirectionFix ×3). −31 dead tests (TestCalculateEdge ×5, TestRunNemesis ×26).
  Test suite: 1103 → 1079 (−31 dead, +7 regression) ✅
- **V37_INBOX.md** — Session 29 completion notice + Layer 1 validation request
- **REVIEW_LOG.md** — Session 29 audit summary + ELI5 skill guide + V37 action items
- **CLAUDE.md** — Lessons 43/45 updated; lessons 46 (signed RLM) and 47 (narrative constants = cancer) added; CURRENT PROJECT STATE updated to Session 29; version header updated.
- **memory/MEMORY.md** — Test count updated, critical bug section replaced with Session 29 summary, Next Session Targets updated.
- **memory/ORIGINAL_PROMPT.md** — Full session 29 state, module table, commit hash, next targets.

### V37 Coordination
- V37 notified via V37_INBOX.md: validate _canonical_totals_books() matches Layer 1 spec
- V37 action items written to REVIEW_LOG.md

### Tests
1103 → 1079 passing ✅ (net: −24 = −31 dead tests, +7 regression tests)

### Commits
- f6a4b3c — Session 29: full math audit + bug fixes + dead code removal — PUSHED ✅

### Live Bet Status
4 logged (0 resolved). Analytics gate = 10 resolved bets. Totals bets NOW UNBLOCKED.

---

## Session 25 — 2026-02-24

### Objective
Build analytics Phase 1 dashboard (07_analytics.py), migrate bet_log schema (+7 analytics columns),
update bet tracker form for analytics metadata capture. Fix V37 audit flags. Run session end ritual.

### What Was Built
- **core/line_logger.py** — schema migration: 7 new columns via `_BET_LOG_MIGRATIONS` idempotent ALTER TABLE:
  `sharp_score INTEGER DEFAULT 0`, `rlm_fired INTEGER DEFAULT 0`, `tags TEXT DEFAULT ''`,
  `book TEXT DEFAULT ''`, `days_to_game REAL DEFAULT 0.0`, `line REAL DEFAULT 0.0`, `signal TEXT DEFAULT ''`
  `log_bet()` signature extended: all 7 new params optional with defaults — existing callers unaffected.
- **core/analytics.py** (NEW — 7 pure functions, source-agnostic list[dict] API):
  `get_bet_counts`, `compute_sharp_roi_correlation`, `compute_rlm_correlation`, `compute_clv_beat_rate`,
  `compute_equity_curve`, `compute_rolling_metrics`, `compute_book_breakdown`
  MIN_RESOLVED=30 gate (matches calibration.py). _pearson_r() returns None on <3 pairs or zero variance.
  Zero imports from core/ — stdlib only.
- **tests/test_analytics.py** (NEW — 51 tests across 9 test classes — all passed immediately)
- **pages/07_analytics.py** (NEW — Phase 1 dashboard):
  6 sections: Sharp score ROI bins + Pearson r, RLM lift, CLV beat rate, Equity curve, Rolling 7/30/90d, Book breakdown
  IBM Plex Mono + IBM Plex Sans. Sample guards (amber-bordered) before every section (N < 30).
  st.html() for cards, st.bar_chart() for ROI bins, st.line_chart() for equity curve.
- **pages/04_bet_tracker.py** — Log Bet form extended with 7 analytics metadata fields
  (sharp_score, line, book, rlm_fired, days_to_game, signal, tags). V37 flag fix: added days_to_game.
- **CLAUDE.md** — Session 25 updates: version bump, SHARP_THRESHOLD gate (0/20 → 0/5), lesson 23 fix,
  lessons 26-32 added, CURRENT PROJECT STATE fully replaced (was frozen at Session 17 / 1011 tests).
- **PROJECT_INDEX.md** — test count updated (1011 → 1062), analytics.py + 07_analytics.py added.
- **V37_INBOX.md** — Session 26 tasks written: v36 originator_engine caller fix, nhl_data promotion.
- **memory/ORIGINAL_PROMPT.md** — Session 25 state, new modules, new lessons, updated next targets.

### V37 Audit (Session 25)
APPROVED. Two minor flags raised and fixed:
1. `days_to_game` missing from Log Bet form → ✅ fixed (effac79)
2. `analytics.py` comment wrong (`matches calibration.py` → `matches MIN_BETS_FOR_CALIBRATION in calibration.py`) → ✅ fixed (effac79)
V37 confirmed: originator_engine bug in v36 (sandbox callers fully correct), nhl_data 163/163 baseline.
V37 confirmed: v36 Supabase bet_history needs 7 new columns before analytics.py promotes (names already match).

### Tests
1011 → 1062 (+51), 1062/1062 passing ✅

### Architectural Decisions
- analytics.py: source-agnostic list[dict] API. Pages pass get_bets() (SQLite) or fetch_bets() (Supabase v36). Zero rewrites on promotion.
- Form parity rule: any log_bet() param additions must ship with 04_bet_tracker.py form update same session.
- Sandbox originator_engine callers: all use efficiency_gap_to_margin(gap) as mean — fully correct. V37 owns v36 fix.

### Commits
- 8e5c1ff — Session 25: analytics Phase 1 build + 51 tests ✅
- effac79 — V37 flag fixes (days_to_game + analytics.py comment)
- 834ad6f — coordination files (REVIEW_LOG.md + V37_INBOX.md)
- [this commit] — CLAUDE.md + PROJECT_INDEX.md + session end files

---

## Session 24 — 2026-02-24

### Objective
Establish permanent automated workflow protocols, safety rails, backup system, and Two-AI accountability infrastructure.

### What Was Built
- **CLAUDE.md** — major update (Session 24):
  - Access rules: titanium-v36 now R+W for this chat (coordination/specs only); Macbook system files permanently forbidden
  - Skills mandate: sc:index-repo, sc:save, sc:analyze, sc:brainstorm, sc:research, frontend-design, claude-md-management, verification-before-completion — all REQUIRED
  - Two-AI access rules: V37 = R-only to sandbox, this chat = R+W to sandbox + V36
  - Credit budget section: 300/500/1000 constants documented
  - Backup system section documented
  - Loading screen tips required on every response
- **scripts/backup.sh** (new): timestamped .tar.gz of sandbox + V36, keeps last 5, max 200MB cap, storage guard
- **.gitignore**: .backups/ excluded from commits
- **core/odds_fetcher.py**: SESSION_CREDIT_SOFT_LIMIT=300, SESSION_CREDIT_HARD_STOP=500, BILLING_RESERVE=1000
  - QuotaTracker: session_used tracking, is_session_hard_stop(), is_session_soft_limit()
  - report() updated with session usage display
  - fetch_batch_odds() uses is_session_hard_stop() (replaces is_low(20))
- **tests/test_odds_fetcher.py**: +4 quota tests, setup_method() added to batch test classes, _reset_quota() helper

### Tests
1007 → 1011 (+4), 1011/1011 passing ✅

### Architectural Decisions
- Session credit budget self-imposed (not from API) — session_used tracked via header delta, falls back to last_cost
- Backup script stores inside sandbox (.backups/) to stay within write permissions; gitignored
- BILLING_RESERVE=1000 is the global floor — exists independently of session budget

### Gates Changed
None. (SHARP_THRESHOLD 45, RLM 0/5, B2B 0/10, CLV 0/30)

### Session 24 (continued) — 2026-02-24 — V37 Auto-Coordination + Access Architecture

**What was built:**
- **V37_INBOX.md** (new, in sandbox root): auto-relay from sandbox to V37 reviewer. V37 reads at startup via updated CLAUDE.md. Eliminates user relay entirely.
- **memory/ORIGINAL_PROMPT.md**: session transition template. Always updated before opening new sandbox chat.
- **memory/REVIEWER_PROMPT.md**: V37 reviewer startup prompt (copy-paste to start new V37 session). Maintained here in sandbox.
- **CLAUDE.md updates**: titanium-v36 demoted to READ-ONLY forever. Sandbox = single write domain. 2-session save hard rule added. Lessons #22-25 added.
- **MEMORY.md**: updated with Session 24 complete state + session transition protocol section.

**Access architecture finalized (permanent):**
- Sandbox writes: ~/ClaudeCode/agentic-rd-sandbox/ ONLY
- V37 writes: ~/Projects/titanium-v36/ ONLY
- Each chat reads from the other — no cross-repo writes

**Commits:** d85a1f2, 7f9994a, 0395926 (sandbox) | c464bfe, 0c18e27 (titanium-v36)
**Pending push:** 7f9994a + 0395926 to sandbox GitHub (needs token)

---

## Session 23 — 2026-02-24

### Objective
KOTC side mission (DraftKings King of the Court promo) + build long-term KOTC module + workflow change announcement.

### KOTC Side Mission Deliverable (Tonight Feb 24, 2026)
- Slate: 11 games, 22 teams
- **#1 Pick: Luka Doncic (LAL vs ORL, 10:30 PM ET)** — proj PRA ~48, triple-double machine, 53.73 DFS, proven KOTC winner
- **#2 Pick: Jalen Johnson (ATL vs WAS, 7:30 PM ET)** — proj PRA ~42, GREAT matchup (WAS bottom-5 defense), reliable floor
- **#3 Pick: Tyrese Maxey (PHI vs IND, 7:00 PM ET)** — proj PRA ~36-47; ceiling unlocks if Embiid (questionable) sits
- **Eliminated:** Jaylen Brown (BOS) confirmed OUT — bruised right knee (DK Network's primary pick)
- **Value pick:** Kevin Porter Jr. (MIL vs MIA) — proj PRA ~39, career-high reb/ast, low public ownership

### Key Research Findings
- DK Network's pre-injury pick was Jaylen Brown; article published before injury confirmed
- Luka Doncic traded to LAL (2025-26 season); Kevin Porter Jr. on MIL (career year)
- Embiid is questionable — if he sits, Maxey virtual profile activates (47.7 raw PRA)

### What Was Built

#### 1. `core/king_of_the_court.py` — NEW MODULE (74 tests)
PRA-ranked KOTC analyzer. Zero API cost — static 2025-26 season averages.

**Key components:**
- `_PlayerProfile`: 55 player profiles (name, team, pts/reb/ast/ceil_mult/min_pg)
- `_TEAM_DEF_RATING`: 30-team defensive ratings (108-122 scale), lower = harder matchup
- `_matchup_multiplier()`: opponent quality → PRA scale factor (0.90-1.18)
- `_kotc_score()`: 0-100 composite = 60% proj + 30% ceiling + 10% TD threat + matchup bonus
- `rank_kotc_candidates()`: accepts injury_outs (set), star_outs (dict), opponent_map
- Virtual Maxey-Embiid-out profile: activates automatically when Embiid in injury_outs
- `is_kotc_eligible_day()`: Tuesday gate (weekday==1)

**KOTC Score formula reference points:**
- Jokic (50 PRA, 62.5 ceiling, TD): base=54.5, ceil=26.8, TD=10 → 91.3
- Luka Doncic (47.4 PRA, 57.8 ceiling, TD): → ~86.5
- Jalen Johnson (42.3 PRA, 48.6 ceiling, TD): → ~73
- Maxey w/Embiid out (47.7 PRA, 58.3 ceiling): → ~77

#### 2. `pages/01_live_lines.py` — KOTC sidebar widget
- Renders only on Tuesdays (`is_kotc_eligible_day()`)
- Top-3 candidate cards with KOTC score, projected PRA, ceiling, matchup grade
- DNP text input → live re-rank via injury_outs
- Star-out input ("Player Name (TEAM)") → role_expansion boost
- Virtual Maxey profile upgrade shown with ↑ badge

#### 3. `PROJECT_INDEX.md` — updated (sc:index-repo)
- Reflects all 17 modules, 1007 tests
- Added: nba_pdo, king_of_the_court, calibration, injury_data, parlay_builder, originator_engine, weather_feed, 06_simulator

### Test Count
- 1007 / 1007 passing (+74 new KOTC tests)

### Commits This Session
- 60d83e2 — injury leverage sidebar + NUCLEAR score boost
- 85926af — KOTC module (core/king_of_the_court.py + tests + UI)
- ff4f3e6 — PROJECT_INDEX.md update

### Pending Pushes (need GitHub token: Contents Read+Write)
- 583621f (NBA PDO) + 60d83e2 + 85926af + ff4f3e6 + any SESSION_LOG commit

### Workflow Change Announced
- V36 chat confirmed sandbox superior; transitioning to reviewer role
- This chat = frontier development; V36 = code reviewer
- titanium-experimental on sabbatical
- Two-AI bridge: shared REVIEW_LOG.md + future reviewer_bridge.py
- Documented in MEMORY.md under "Workflow Change" and "Two-AI Bridge Plan"

### Architecture Lessons
- KOTC uses `_endpoint_factory`-free design (static data only — no network)
- Virtual profile pattern for conditional player upgrades (Embiid-out → Maxey boost)
- Pairing assumption for opponent_map: teams[0]↔teams[1], teams[2]↔teams[3], etc.
- DFS FPTS ≠ raw PRA: DK scoring = 1pt/1.25reb/1.5ast; KOTC uses raw P+R+A only

---

## Session 14 — 2026-02-19

### Objective
Wire the efficiency component into the Sharp Score pipeline (it was always 0.0).
Run system gates check, W6 tennis tier check. Build `core/efficiency_feed.py`.

### System Gates (checked at session start)
- RLM fire count: 0/20 — in-memory counter, gate NOT met
- CLV/graded bets: 0 — gate NOT met
- NBA B2B instances: 13 events/2 dates only — gate NOT met (need 10+ confirmed B2B)
- W6 tennis: RESOLVED (see below)

### W6 — Tennis Tier Confirmation
- Odds API key `01dc7be6ca076e6b79ac4f54001d142d` verified.
- `GET /v4/sports/` returns 83 sports total.
- `tennis_atp_qatar_open` (active=True) and `tennis_wta_dubai` (active=True) both present.
- **Tennis IS on this API tier.** No upgrade needed.
- Next gate: build tennis kill switch (surface + H2H data = api-tennis.com $40/mo decision).
  See MASTER_ROADMAP Section 3C for spec. Gated on user approval for $40/mo spend.

### What Was Built

#### 1. `core/efficiency_feed.py` — NEW MODULE
Team efficiency data layer. 250+ canonical teams across 10 leagues/sports.

**Data coverage**:
- NBA: 30 teams (Net Rating × 2.2 → adj_em)
- NCAAB: 80+ programs (KenPom/Barttorvik AdjEM)
- NFL: 32 teams (EPA/play × 80.0)
- MLB: 30 teams ((4.30 − ERA) × 8.0)
- MLS: 27+ clubs (xGD/90 × 15.0)
- EPL: 20 clubs (xG-differential)
- Bundesliga: 18 clubs | Ligue 1: 18 clubs | Serie A: 20 clubs | La Liga: 20 clubs

**Scaling formula** (uniform across all sports):
```
differential = home_adj_em − away_adj_em
gap = (differential + 30) / 60 × 20     # result is 0-20
gap = clamp(gap, 0.0, 20.0)
```
- gap=10.0 → evenly matched
- gap>10.0 → home structural edge
- Unknown team fallback: 8.0 (below neutral — doesn't inflate scores)

**Functions**:
- `get_team_data(team_name)` → direct match, alias lookup, case-insensitive fallback
- `get_efficiency_gap(home, away)` → 0-20 float. Returns 8.0 if either team unknown.
- `list_teams(league=None)` → canonical team names, optional league filter
- 70+ aliases (NBA/NFL short names, soccer abbreviations)

**Architecture**: NO imports from other core modules. Pure data.

#### 2. `core/math_engine.py` — UPDATED
`parse_game_markets()` now accepts `efficiency_gap: float = 0.0` parameter.
All three `calculate_sharp_score()` call sites updated from `0.0` to `efficiency_gap`.
Docstring updated with parameter description.

#### 3. `pages/01_live_lines.py` — UPDATED
- Imports `from core.efficiency_feed import get_efficiency_gap`
- Computes `eff_gap = get_efficiency_gap(home, away)` per game in `_fetch_and_rank()`
- Passes `efficiency_gap=eff_gap` to `parse_game_markets()`
- **Sort fixed**: candidates now sorted by `sharp_score` descending (was `edge_pct` — violation of CLAUDE.md rule "Sort: By Sharp Score descending")

#### 4. `tests/test_efficiency_feed.py` — NEW (53 tests)
- `TestGetTeamData`: canonical, alias, case-insensitive, miss, whitespace, all leagues
- `TestGetEfficiencyGap`: formula precision, clamp, unknown fallback, symmetry, cross-sport
- `TestListTeams`: count per league, filter, unknown league, no duplicates
- `TestArchitecture`: confirms no imports from math_engine, odds_fetcher, line_logger

#### 5. `tests/test_math_engine.py` — UPDATED (+5 tests)
- `test_efficiency_gap_zero_default` — default arg leaves efficiency=0 in breakdown
- `test_efficiency_gap_increases_sharp_score` — 15.0 gap > 0.0 gap score
- `test_efficiency_gap_reflected_in_breakdown` — breakdown["efficiency"] == passed gap
- `test_efficiency_gap_capped_at_20` — 25.0 clamps to same score as 20.0

### Test Results
**418/418 passing** (was 363/363). +55 new tests.

### Impact on Sharp Score
Before: efficiency component = 0.0 for all games (up to 20 pts uncaptured).
After: efficiency component = 0-20 for all known teams across 10 leagues.

Example uplift:
- OKC (28.0 em) at home vs Wizards (-21.6 em): gap=16.5 → +16.5 pts to Sharp Score
- Evenly matched NBA game: gap≈10.0 → +10.0 pts to Sharp Score
- Unknown teams: gap=8.0 → +8.0 pts (conservative floor, doesn't inflate)

### Next Session Starting Point (Session 15)
Priority:
1. **Tennis kill switch** — spec in MASTER_ROADMAP Section 3C. $40/mo decision needed first.
   If user approves api-tennis.com, build: surface lookup dict, player name normalization,
   `tennis_kill_switch()`, add tennis_atp/tennis_wta to SPORT_KEYS.
2. **NBA B2B home/road differentiation** — waiting for 10+ B2B instances in DB.
3. **MLBkill switch** — Apr 1 gate. Not yet.

---

## Session 13 — 2026-02-19

### Objective
Build NHL kill switch pipeline: goalie starter detection → kill switch logic → scheduler wiring.
Research from Session 12 confirmed NHL boxscore API is free, public, no key required.
Goal: activate NHL from collar-only to full kill-switch-equipped sport.

### What Was Built

#### 1. `core/nhl_data.py` — NEW MODULE
NHL goalie starter detection from free NHL Stats API.

**Functions**:
- `normalize_team_name(name)` — Odds API team name → NHL abbrev (BOS/NYR/etc.)
  - Handles: full name, abbrev passthrough, last-word match, case-insensitive
  - All 32 NHL teams + Utah Hockey Club
- `get_nhl_game_ids_for_date(date_str, session)` — Today's schedule via `api-web.nhle.com/v1/schedule/{date}`
  - Returns: list of {game_id, away_team, home_team, game_start_utc, game_state}
  - Returns [] on API error (graceful degradation)
- `get_nhl_starters_for_game(game_id, session)` — Boxscore via `api-web.nhle.com/v1/gamecenter/{id}/boxscore`
  - Returns None when game is in FUT state (no playerByGameStats)
  - Returns None when no goalies populated (still loading)
  - Returns structured dict with away/home starter_confirmed + starter_name + backup_name
- `get_starters_for_odds_game(away, home, game_start_utc, session)` — High-level: name→abbrev→game_id→boxscore
  - Timing gate: returns None if >90 min before game start (too early, FUT state)
  - Returns None if team name normalization fails or no matching game in schedule

**Module-level goalie cache**:
- `_goalie_cache: dict[str, dict]` — keyed by Odds API event_id
- `cache_goalie_status(event_id, status)` — scheduler writes here
- `get_cached_goalie_status(event_id)` — parse_game_markets() reads here
- `clear_goalie_cache()` + `goalie_cache_size()` — testing utilities

**Architecture**: Zero imports from math_engine, odds_fetcher, line_logger, or scheduler.
No API key required. Zero quota cost. Returns None on all failure paths (never raises).

#### 2. `core/math_engine.py` — `nhl_kill_switch()` added

```python
def nhl_kill_switch(
    backup_goalie: bool,
    b2b: bool = False,
    goalie_confirmed: bool = True,
) -> tuple[bool, str]:
```

**Fires (KILL)**: backup_goalie=True → "KILL: Backup goalie confirmed — require 12%+ edge to override"
**Flags (FLAG)**:
- b2b=True → "FLAG: B2B — reduce Kelly 50%"
- goalie_confirmed=False → "FLAG: Goalie not yet confirmed — require 8%+ edge"
**Safe**: All False → ("", False)

Priority: backup kill overrides b2b flag. b2b overrides unconfirmed flag.

**parse_game_markets() updated**:
- New optional param: `nhl_goalie_status: Optional[dict] = None`
- When sport=="NHL" and nhl_goalie_status provided:
  - Determines per-candidate opponent goalie status (away bet → care about home goalie)
  - Calls nhl_kill_switch() and sets c.kill_reason on each candidate
- When sport=="NHL" and nhl_goalie_status=None:
  - Applies FLAG(goalie not confirmed) to all NHL candidates (safe default)

#### 3. `core/scheduler.py` — NHL goalie poll wired in

**New function**: `_poll_nhl_goalies(games)` — internal, called by `_poll_all_sports()`
- For each NHL game: checks if commence_time is within 90 min window
- Calls `get_starters_for_odds_game()` for qualifying games
- Writes results to `nhl_data.cache_goalie_status(event_id, data)` when starters confirmed
- Errors are swallowed (logger.warning) — no goalie data = FLAG not crash

**`_poll_all_sports()` updated**:
- Added: `if sport == "NHL": _poll_nhl_goalies(games)` after existing probe logic
- Import added: `from core.nhl_data import get_starters_for_odds_game, cache_goalie_status`

### Tests Added

| File | New Tests | Total |
|---|---|---|
| tests/test_nhl_data.py | 34 (new file) | 34 |
| tests/test_math_engine.py | 10 (TestNhlKillSwitch) | ~160 |
| tests/test_scheduler.py | 5 (TestNhlGoaliePoll) | 35 |
| **Session total** | **49** | **363** |

**363/363 passing** (was 314/314)

### Kill Switch Status Update

| Sport | Kill Switch | Before | After |
|---|---|---|---|
| NHL | Goalie starter detection | ⚠️ Collar-only | ✅ Full kill switch |

### Architecture Decisions

1. **Goalie cache in nhl_data.py** (not scheduler): Keeps scheduler thin. parse_game_markets()
   can read it without scheduler coupling.
2. **nhl_goalie_status as parse_game_markets() param**: Clean — math_engine stays pure (no I/O),
   UI/pages pass the cached value when calling parse_game_markets for NHL games.
3. **FUT state = FLAG (not KILL)**: returning None from boxscore = goalie not confirmed = require
   higher edge. Not a hard kill — market might still be good without the kill signal.
4. **90-min window**: Matches when NHL API actually populates `playerByGameStats`.
   Before that, rosters haven't finalized and starter field is absent.

### Next Session Targets (Session 14)

From MASTER_ROADMAP Section 9 (updated):

1. **Check system gates**:
   - RLM gate sidebar: if RAISE READY (≥20 fires), manually raise SHARP_THRESHOLD 45→50
   - Bet tracker: if ≥10 graded bets, build CLV vs edge% scatter (Analysis ③, item 4A)
2. **3D. NBA Home/Road B2B** — add `is_home_b2b` param once 10+ B2B instances in DB
3. **W6**: Confirm tennis_atp in current Odds API tier (needs good wifi + API key)
4. **MLB kill**: HOLD until Apr 1 gate. Season starts Mar 27.

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
