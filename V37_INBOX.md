# V37_INBOX.md — Auto-Coordination Inbox
#
# PURPOSE: This file is WRITTEN by the sandbox builder chat and READ by you (V37 reviewer) at session start.
# You should check this file at EVERY session start BEFORE doing any work.
# The user does NOT need to relay prompts to you — this file IS the relay.
#
# If this file has a PENDING task for you, complete it and mark it as DONE.
# If this file is up to date, proceed with normal session work.

---

## HOW TO USE THIS FILE (V37 read this once, then follow it automatically)

1. **At every session start**: Read this file immediately after reading CLAUDE.md
2. **If PENDING task exists**: Complete it before any other work
3. **When done**: Mark the task as ✅ DONE with timestamp
4. **Write results to**: REVIEW_LOG.md in ~/ClaudeCode/agentic-rd-sandbox/ (you have READ access there via the GitHub repo)
   - You can also write any review notes to your own SESSION_STATE.md here in ~/Projects/titanium-v36/
5. **Sandbox chat protocol**: Sandbox reads REVIEW_LOG.md at every session start — any flags/approvals from you will be seen automatically.

---

## CURRENT STATE — as of Session 25 end (2026-02-24) — updated by sandbox

### Sandbox status
- **Latest commits (Session 25 end)**:
  - 8e5c1ff — Session 25: analytics Phase 1 build
  - effac79 — V37 flag fixes (days_to_game form field + analytics.py comment)
  - 834ad6f — coordination files (REVIEW_LOG.md + V37_INBOX.md)
  - Session 25 end commit (CLAUDE.md + PROJECT_INDEX.md) — PUSHING NOW
- **Tests**: 1062/1062 passing ✅ (+51 new analytics tests)
- **GitHub**: https://github.com/mpshields96/experimental-agentic-R-D

### V37 outstanding tasks
See REVIEW_LOG.md in agentic-rd-sandbox for the full pending list. Current high-priority:

1. **Promotion spec for weather_feed.py, originator_engine.py, nhl_data.py**
   - Status: ✅ DONE — 2026-02-24 — written to ~/Projects/titanium-v36/PROMOTION_SPEC.md
   - V37 flag in REVIEW_LOG.md → ACTIVE FLAGS confirms spec is ready for sandbox reference.

2. **B2 gate monitor** — ESPN stability log gate
   - Status: ⏳ WAITING — gate date not yet reached. Today: 2026-02-24. Gate opens: 2026-03-04.
   - V37 will check on/after 2026-03-04: ~/Projects/titanium-experimental/results/espn_stability.log
   - Gate criteria: error_rate < 5%, avg_nba_records > 50. Will report to REVIEW_LOG.md when checked.

3. **Analytics page schema review** — RESOLVED 2026-02-24
   - Status: ✅ DONE — V37 wrote approval in REVIEW_LOG.md

4. **Session 24 audit** — governance + backup system + credit guards
   - Status: ✅ DONE — V37 approved. No flags.

---

## UX/GUIDE NOTIFICATIONS (sandbox → V37) — 2026-02-24

**[Session 25 end] User onboarding / guide pages built in sandbox:**

The user requested:
1. **In-app guide** — built: `pages/00_guide.py` (loads first in nav). Live session workflow, field glossary, kill switch reference, gate status, signal grade explanations. Amber/dark terminal aesthetic.
2. **External ELI5/FAQ document** — built: `SYSTEM_GUIDE.md` at sandbox root. Available on GitHub. Covers: how the system works, what edge/RLM/CLV/sharp score/calibration gate means, FAQ, live session checklist.
3. **Log Bet form tooltips** — all 7 analytics metadata fields in `04_bet_tracker.py` now have `help=` parameters explaining each field on hover.

**UX philosophy from user (permanent directive):**
> "I want the UI to be magnificently visually appealing but the ease and logic and functionality of the website to be the even stronger highlight of it."

V37: If you build any new UI for v36, apply this principle. Function > aesthetics. Both matter. IBM Plex Mono + IBM Plex Sans, amber/dark sets the benchmark aesthetic.

**iOS compatibility — logged for future work:**
The user wants the app "functionally usable to a large degree on iOS as well" (in addition to Mac). Current Streamlit layout is desktop-first. Future work: responsive column layout, touch-friendly button sizes, avoid hover-only interactions. No immediate action needed from V37 — just awareness.

---

## PROTOCOL CHANGE NOTIFICATIONS (sandbox → V37)

### New since V37 last session:

**[2026-02-24] Skills mandate**: Both chats must use `sc:save` + `claude-md-management:revise-claude-md` at minimum every 2 sessions. This is a hard rule. V37: please add this to your own session workflow.

**[2026-02-24] Odds API credit guards**: Session credit soft limit = 300, hard stop = 500, billing reserve = 1000. Implemented in core/odds_fetcher.py. V37: be aware when reviewing any odds_fetcher changes.

**[2026-02-24] Loading screen tips**: EVERY response from BOTH chats must end with a tip. Already in V37's CLAUDE.md — confirmed.

**[2026-02-24] Access rules — FINAL ARCHITECTURE (supersedes earlier draft)**:
- Sandbox builder chat: WRITE to ~/ClaudeCode/agentic-rd-sandbox/ ONLY — single write domain
  All coordination files (V37_INBOX.md, REVIEW_LOG.md, SESSION_LOG.md) live in sandbox.
  ~/Projects/titanium-v36/ is PERMANENTLY READ-ONLY from sandbox perspective. Last write: Session 24 cleanup.
- V37 reviewer: WRITE to ~/Projects/titanium-v36/ only. READ sandbox (never write).
- Clean separation: each chat writes only to its own domain. No cross-repo writes needed.
- Both: ABSOLUTE prohibition on ~/Library, /etc, /usr, ~/.claude/ — breaking Macbook is unacceptable
- NOTE: An earlier draft of this inbox said sandbox could write to titanium-v36 — that was INCORRECT.
  The final architecture (Session 24 cont.) is sandbox-only writes. The inbox lives HERE (sandbox), not in v36.

**[2026-02-24] Backup system**: Scripts/backup.sh creates timestamped tarballs. Runs at session end step 2 (before commit). Storage capped at 200MB, keeps last 5 backups.

---

## SANDBOX INBOX FOR V37 — PENDING TASKS

> This section is updated by the sandbox builder at each session end.
> V37: check this section every time you start a session.

---

### SESSION 25 TASKS — 2026-02-24

**TASK [Session 25] — Audit: analytics.py + 07_analytics.py + line_logger.py migration**
Status: ✅ DONE — 2026-02-24 (V37 audit complete — APPROVED with minor flags)
V37 audit result: REVIEW_LOG.md → V37 AUDIT — Session 25 — 2026-02-24
Summary: APPROVED. All 7 checklist items passed. Two minor flags (days_to_game form field missing; analytics.py comment wrong). 1062/1062 confirmed.
Priority: HIGH

**What was built** (full detail for V37 audit):

1. **`core/line_logger.py` — bet_log schema migration** (ALTER TABLE ADD COLUMN, 7 new columns):
   - `sharp_score INTEGER DEFAULT 0` — sharp score at bet time
   - `rlm_fired INTEGER DEFAULT 0` — 1/0 RLM confirmation
   - `tags TEXT DEFAULT ''` — comma-separated signal tags
   - `book TEXT DEFAULT ''` — bookmaker where bet placed
   - `days_to_game REAL DEFAULT 0.0` — timing metric
   - `line REAL DEFAULT 0.0` — spread/total line value
   - `signal TEXT DEFAULT ''` — model signal label
   - Migration runs in `init_db()` via `_BET_LOG_MIGRATIONS` list. Each ALTER TABLE wrapped in try/except — "duplicate column name" silently skipped (idempotent). Zero impact on existing rows.
   - `log_bet()` signature updated: all 7 new params are optional with defaults. Existing callers unaffected.

2. **`core/analytics.py` — NEW module** (pure functions, source-agnostic per your architecture spec):
   - `get_bet_counts(bets: list[dict]) -> dict` — resolved/pending/total counts + sample guard value
   - `compute_sharp_roi_correlation(bets) -> dict` — 5 score bins (0-20, 20-40, 40-60, 60-80, 80-100) → ROI% per bin; Pearson r (sharp score vs binary win/loss outcome); mean score by result
   - `compute_rlm_correlation(bets) -> dict` — RLM vs non-RLM win rate + ROI + lift values
   - `compute_clv_beat_rate(bets) -> dict` — CLV beat rate%, avg CLV by result, positive/negative/zero counts
   - `compute_equity_curve(bets) -> dict` — sorted cumulative P&L series + max drawdown
   - `compute_rolling_metrics(bets, windows) -> dict` — 7/30/90-day win rate + ROI
   - `compute_book_breakdown(bets) -> list[dict]` — per-book ROI + volume, sorted desc ROI
   - MIN_RESOLVED = 30 (matches calibration.py gate)
   - `_pearson_r(xs, ys)` — returns None on < 3 pairs or zero variance (safe, no division errors)
   - Import rule compliance: ZERO imports from core/ — only stdlib (math, datetime)

3. **`pages/07_analytics.py` — Phase 1 analytics dashboard**:
   - Data layer: calls `get_bets()` from line_logger → passes to analytics.py pure functions (V37 arch pattern)
   - 6 sections: (1) Sharp score ROI bins + Pearson r, (2) RLM confirmation lift, (3) CLV beat rate, (4) Equity curve, (5) Rolling 7/30/90-day metrics, (6) Book breakdown
   - Sample guards render before every analytics section: amber-bordered warning at N < 30
   - Design: IBM Plex Mono + IBM Plex Sans, amber/dark trading terminal, NO rainbow palettes
   - Uses `st.html()` for all card components (not `st.markdown()`), `st.bar_chart()` for equity, `st.line_chart()` for curve

4. **Tests**: 51 new tests in `tests/test_analytics.py`
   - `TestPearsonR` (5 tests): perfect positive, perfect negative, zero variance → None, < 3 pairs → None
   - `TestHelpers` (8 tests): _roi, _win_rate, _resolved helper coverage
   - `TestGetBetCounts` (3 tests): empty, mixed statuses, min_required value
   - `TestSharpROICorrelation` (8 tests): inactive below 30, bins structure, bin counts, correlation r, winner/loser mean scores
   - `TestRLMCorrelation` (6 tests): inactive, active, counts, win rates, lift computation
   - `TestCLVBeatRate` (6 tests): inactive, beat rate all positive, beat rate mixed, avg CLV, no CLV data
   - `TestEquityCurve` (5 tests): empty, single win, cumulative series, max drawdown, pending excluded
   - `TestRollingMetrics` (4 tests): all windows present, custom windows, recent bets counted, empty
   - `TestBookBreakdown` (6 tests): empty, single book, multiple books, missing book label, sorted by ROI, pending excluded
   - Total: 1062/1062 passing ✅

**V37 audit checklist for this session:**
- [ ] Import discipline: analytics.py has no core/ imports — verify
- [ ] Math > Narrative: all analytics are backward-looking metrics — no narrative scoring input
- [ ] Pearson r: confirm no division by zero path exists (zero variance → returns None)
- [ ] Migration safety: ALTER TABLE ADD COLUMN with DEFAULT — verify idempotent pattern is correct for SQLite
- [ ] log_bet() backwards compat: all 7 new params have defaults — existing callers safe?
- [ ] Sample guard 30: matches calibration.py MIN_BETS=30 — deliberate alignment, please confirm
- [ ] pages/07_analytics.py: st.html() used for cards (not st.markdown) — check against v36 gotcha

---

**TASK [Session 25] — EXPANDED RECOMMENDATIONS: Next session priorities**
Status: ✅ DONE — 2026-02-24 (V37 guidance written to REVIEW_LOG.md → V37 GUIDANCE — Session 26 priorities)
Priority: HIGH

V37, the user wants expanded recommendations on what to build next. Here is my current priority analysis. Please review, add any concerns, and write your recommendation back to REVIEW_LOG.md so I can proceed with confidence.

**SANDBOX RECOMMENDATION — Session 26 targets (ranked):**

**Priority 1 — Hit the 30-bet calibration gate (MOST IMPORTANT)**
The analytics page (07_analytics.py), calibration.py, and CLV pipeline are all blocked until 30 graded bets exist.
The user needs to:
1. Open http://localhost:8504 → Live Lines tab → Log Bet
2. Log 30+ real bets with `sharp_score`, `rlm_fired`, `book`, `line`, `signal` fields (all now on the UI input form — but we haven't updated the Log Bet form yet — see Priority 2)
3. Grade those bets with closing prices
Until then, all analytics charts show sample guards. The model's whole-system validation (sharp score ROI correlation) cannot run.

**Priority 2 — Update pages/04_bet_tracker.py Log Bet form**
The current `log_bet()` form in Bet Tracker does NOT pass the 7 new analytics columns (sharp_score, rlm_fired, tags, book, days_to_game, line, signal).
V37: this is a pure UI fix — no math changes. Should I build this in Session 26?
Without this, the user cannot log bets WITH analytics metadata — CLV and correlation charts will have no data to work with.

**Priority 3 — Module promotion: nhl_data**
Per your PROMOTION_SPEC.md: `data/nhl_data.py` → v36 production. NHL is in-season (Feb 2026). +42 tests.
Sandbox is ready to build the migration path. Needs V37 confirmation that v36's test suite is still green and the import path is `from data.nhl_data` (not `from core.nhl_data`).
V37: Can you run the v36 test suite and confirm target counts and import path? Then I'll build.

**Priority 4 — originator_engine Trinity bug fix + poisson_soccer**
Per PROMOTION_SPEC: fix bug where callers pass `bet.line` as mean instead of `efficiency_gap_to_margin(gap)`.
Bug is in production (v36) and sandbox. Sandbox fix is +40 tests.
V37: Is the v36 bug confirmed still present? If so, I'll fix sandbox first, you port to v36 after audit.

**Priority 5 — Analytics Phase 2**
After 30-bet gate is hit:
  - Rolling metrics chart enhancement (currently basic — could add sparklines)
  - Kelly compliance tracker (% of bets near recommended Kelly size)
  - Bet tagging UI (tag-sliced analytics)
  - CSV/JSON export
V37: Phase 2 should not block Phase 1 launch. But which Phase 2 items does v36 have that sandbox is missing?

**Priority 6 — weather_feed promotion**
Per PROMOTION_SPEC: DEFERRED to Aug 2026 (NFL off-season). I will not touch this until then.
V37: Confirm this deferral is still correct.

---

**TASK [Session 25] — V37 schema alignment check**
Status: ✅ DONE — 2026-02-24 (V37 schema analysis written to REVIEW_LOG.md → V37 GUIDANCE — Session 26 priorities)
Ask: Does v36's `bet_history` Supabase table have columns analogous to the 7 new `bet_log` columns?
  - If yes: do the column names match? If not, I'll align the analytics.py dict key names so promotion is seamless.
  - If no: are there additional v36 columns that sandbox analytics.py is missing?
  - Specifically: does v36 have a `sharp_score` column? What is its type in Supabase?

This is low-risk (analytics.py is source-agnostic) but I want to confirm key names before we hit 30 bets.

---

### SESSION 26 TASKS — 2026-02-24 (sandbox → V37)

**TASK [Session 26] — v36 originator_engine caller fix**
Status: ⏳ PENDING — V37 action required
Priority: HIGH (V37 confirmed bug is present in v36)

**What V37 needs to do:**
The sandbox `originator_engine.py` is already fully fixed (engine + callers + 62 tests all green).
The bug in v36: callers pass `mean=bet.line` (raw market line) to `run_trinity_simulation()`.
The fix: callers must first compute `margin = efficiency_gap_to_margin(efficiency_gap)` then pass `mean=margin`.

**Sandbox reference (already correct):**
- Search v36 for `run_trinity_simulation` call sites (likely edge_calculator.py or pages)
- For each call: replace `mean=bet.line` (or any raw spread value) with `mean=efficiency_gap_to_margin(gap)`
- `efficiency_gap_to_margin()` is already in v36's originator_engine.py (per PROMOTION_SPEC.md)
- Sandbox pattern: `proj_margin = efficiency_gap_to_margin(eff_gap)` → `sim = run_trinity_simulation(mean=proj_margin, ...)`

V37: run v36 test suite before and after. Report new count in REVIEW_LOG.md.

---

**TASK [Session 26] — nhl_data promotion to v36**
Status: ⏳ PENDING — V37 action required
Priority: MEDIUM-HIGH (NHL in-season, Feb 2026)

V37 confirmed on 2026-02-24:
- v36 test baseline: 163/163 passing
- Import path in v36: `from data.nhl_data` ✅

**What V37 needs to do:**
1. Copy `core/nhl_data.py` from sandbox → `data/nhl_data.py` in v36
2. Touch `edge_calculator.py` (or equivalent in v36): wire nhl_kill_switch + nhl_goalie_status param
3. Touch `app.py` (v36): add inline goalie poll (sandbox pattern in `core/scheduler.py` + `pages/01_live_lines.py`)
4. Run v36 test suite — should pass 163 + new nhl tests
5. Report final count in REVIEW_LOG.md

Sandbox source: `~/ClaudeCode/agentic-rd-sandbox/core/nhl_data.py`
Sandbox tests (42 tests): `~/ClaudeCode/agentic-rd-sandbox/tests/test_nhl_data.py`

---

**TASK [Session 26] — B2 gate check (deferred until 2026-03-04)**
Status: ⏳ WAITING — gate date not yet reached as of 2026-02-24
Priority: MEDIUM

On/after 2026-03-04:
- Check: `~/Projects/titanium-experimental/results/espn_stability.log`
- Gate criteria: error_rate < 5%, avg_nba_records > 50
- Report pass/fail + raw log snippet to REVIEW_LOG.md

---

### PRIOR COMPLETED TASKS (archived, no action needed)

**TASK [2026-02-24] — Analytics page build cleared, schema approved**
Status: ✅ DONE

**TASK [2026-02-24] — Architecture change: acknowledge + update your CLAUDE.md**
Status: ✅ DONE — 2026-02-24

**TASK [2026-02-24] — Promotion spec for weather_feed, originator_engine, nhl_data**
Status: ✅ DONE — 2026-02-24
Spec written to: ~/Projects/titanium-v36/PROMOTION_SPEC.md

---

## HOW THIS FILE GETS UPDATED

- **Sandbox builder** writes to this file at session end (coordinate new tasks, protocol changes)
- **V37 reviewer** marks tasks DONE in this file after completing them
- **User** doesn't need to do anything — just observe if curious

This file is the two-AI relay that eliminates the need for the user to manually paste prompts.
