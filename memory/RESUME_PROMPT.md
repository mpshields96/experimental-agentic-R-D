# RESUME PROMPT — Titanium-Agentic
# Copy-paste this entire block into a new Claude Code chat to resume the project.
# Last updated: Session 23 — 2026-02-24 — 1007/1007 tests passing
# Save a copy of this in Google Docs as a backup.

---

You are resuming work on **Titanium-Agentic** — a personal sports betting analytics platform
built from scratch in a sandboxed R&D environment. You are the primary AI builder.

## IMMEDIATE FIRST ACTIONS (do before anything else)

```
1. Read /Users/matthewshields/ClaudeCode/agentic-rd-sandbox/CLAUDE.md  (rules + role)
2. Read /Users/matthewshields/ClaudeCode/agentic-rd-sandbox/PROJECT_INDEX.md  (full codebase, 3K tokens)
3. Read /Users/matthewshields/ClaudeCode/agentic-rd-sandbox/REVIEW_LOG.md  (V37 reviewer flags)
4. Run: cd ~/ClaudeCode/agentic-rd-sandbox && python3 -m pytest tests/ -q
5. Run: git status
6. Report: "Session N ready. Tests: X/X. V37 flags: [none / FLAG summary]. Ready to work."
```

## WHERE WE ARE (Session 23 complete — 2026-02-24)

**Sandbox location:** `~/ClaudeCode/agentic-rd-sandbox/`
**App:** `streamlit run app.py --server.port 8504`
**GitHub:** `https://github.com/mpshields96/experimental-agentic-R-D.git` (main, fully pushed)
**Tests:** 1007/1007 passing
**Latest commit:** `0d07439` — CLAUDE.md ritual update

### What's built (17 modules, 6 pages):
- `core/math_engine.py` — all betting math (collar, edge, Kelly, sharp score, RLM, CLV, Nemesis)
- `core/odds_fetcher.py` — Odds API wrapper, quota tracking
- `core/line_logger.py` — SQLite WAL: lines, snapshots, bets, movements
- `core/scheduler.py` — APScheduler: poll loop, NHL goalie hook
- `core/nhl_data.py` — free NHL API: goalie starter detection
- `core/tennis_data.py` — surface classification, player win rates (ATP+WTA, 90 entries)
- `core/efficiency_feed.py` — static team efficiency (250+ teams, 10 leagues)
- `core/weather_feed.py` — NFL live wind (Open-Meteo, 32 stadiums, 1hr TTL)
- `core/originator_engine.py` — Trinity Monte Carlo (20C/20F/60M)
- `core/parlay_builder.py` — 2-leg positive-EV parlay finder
- `core/injury_data.py` — static positional impact (5 sports, 50+ positions, zero API)
- `core/nba_pdo.py` — PDO regression kill switch (nba_api free, _endpoint_factory injection)
- `core/king_of_the_court.py` — DraftKings Tuesday KOTC PRA ranker (static, zero API)
- `core/calibration.py` — sharp score calibration (activates at 30 graded bets)
- `core/clv_tracker.py` — CLV snapshot CSV log
- `core/price_history_store.py` — persistent open-price store for multi-session RLM
- `core/probe_logger.py` — bookmaker probe log
- `pages/01_live_lines.py` — full bet pipeline, injury sidebar, KOTC Tuesday widget
- `pages/02_analysis.py` — KPI, P&L, edge/CLV histograms, line pressure
- `pages/03_line_history.py` — movement cards, sparklines, RLM seed table
- `pages/04_bet_tracker.py` — bet log, grading, CLV
- `pages/05_rd_output.py` — math validation dashboard
- `pages/06_simulator.py` — Trinity game simulator (NBA + Soccer Poisson modes)

## TWO-AI ACCOUNTABILITY SYSTEM (Session 23 — PERMANENT)

A V37 reviewer chat (separate Claude Code session in `~/Projects/titanium-v36/`) audits your output.

**Your responsibilities:**
- **Session START:** Read `REVIEW_LOG.md` — if V37 has a FLAG, address it before new work
- **Session END:** Append session summary to `REVIEW_LOG.md` using the template in that file
- The reviewer has VETO authority over: new external APIs, architectural decisions, rule changes
- The reviewer does NOT veto: bug fixes, test additions, feature implementations
- Current V37 status: APPROVED — no outstanding flags as of Session 23

## KEY MATH (never change without explicit instruction)

- Collar: -180/+150 (soccer: -250/+400)
- Min edge: 3.5% | Min books: 2
- Kelly: 0.25x fraction → >60% = 2.0u NUCLEAR, >54% = 1.0u STANDARD, else 0.5u LEAN
- SHARP_THRESHOLD = 45 (raise to 50-55 only after ≥5 live RLM fires)
- NUCLEAR requires ≥90 sharp score. Max base = 85. Injury boost = up to +5.
- RLM: 3% implied prob shift, passive until 2nd fetch

## GATE STATUS (as of Session 23)

- SHARP_THRESHOLD raise: 0/5 live RLM fires ❌ (not met)
- Calibration: 0/30 graded bets logged ❌ (not met — log bets via UI)
- NBA B2B gate: 0/10 B2B instances observed ❌ (not met)
- MLB kill switch: HOLD until Apr 1, 2026

## ABSOLUTE BANS (permanent — never override)

- NEVER write outside `~/ClaudeCode/agentic-rd-sandbox/`
- NEVER touch titanium-v36/, titanium-experimental/, bet-tracker/ (read-only reference allowed)
- NEVER use or suggest api-tennis.com
- NEVER burn Odds API quota unnecessarily (one full fetch per session for seeding)
- NEVER commit with a GitHub token in the remote URL — rotate immediately after push

## PENDING WORK (Session 24 targets)

### High priority:
1. Log first real bets via UI (`http://localhost:8504` → Live Lines → Log Bet)
   → Start CLV/calibration pipeline. Need 30 graded bets to activate calibration.
2. V37 pending audit tasks (from REVIEWER_ONBOARDING.md, still outstanding):
   - Audit core/weather_feed.py, core/originator_engine.py, core/nhl_data.py for v36 promotion spec
   - B2 gate: check `~/Projects/titanium-experimental/results/espn_stability.log` (gate: date ≥ 2026-03-04)
   - Parlay live validation: run build_parlay_combos() on next NBA game day, report to REVIEW_LOG.md

### Architecture work (two-AI bridge):
- `core/reviewer_bridge.py` — structured handoff file for V37 if async review needs to grow
- MLB kill switch — implement after Apr 1, 2026

## ARCHITECTURE RULES (non-negotiable)

- `from core.X import` — NOT root-level imports
- NEVER import math_engine from odds_fetcher (circular)
- NEVER import other core modules into math_engine (pure math only)
- nba_api: use `_endpoint_factory` injection, never `unittest.mock.patch`
- Cache-seeding: seed module cache BEFORE calling kill switch function
- Edge test fixtures: use outlier-book pattern (3 consensus + 1 outlier) to generate >3.5% edge
- Streamlit: `st.html()` for full HTML, inline styles in cards

## ACCUMULATED LESSONS (Sessions 1-23)

1. Use `st.html()` for card rendering — `st.markdown(unsafe_allow_html=True)` is global CSS only
2. APScheduler guard: `st.session_state` prevents restart on every Streamlit rerun
3. SQLite WAL mode required for concurrent scheduler + UI reads
4. Tennis: surface from sport_key string, not from live API
5. efficiency_gap defaults to 8.0 for unknown teams (slightly below neutral)
6. NCAAF kill switch: off-season Feb-Aug + |spread| ≥ 28 → KILL
7. NBA B2B: road B2B → need 8%+ edge; home B2B → Kelly ×50%
8. Soccer 3-way: use no_vig_probability_3way() for draw markets
9. NFL wind: get_stadium_wind() → KILL totals >20mph, FORCE_UNDER >15mph
10. Trinity bug (fixed): use efficiency_gap_to_margin() as mean, not raw market line
11. RLM passive until 2nd fetch — cold cache → no RLM signal on first poll
12. NHL: nhl_api free tier returns "LA Kings" not "Los Angeles Kings" — normalize_team_name()
13. Parlay: same event_id or same matchup = correlated legs → auto-reject
14. Injury: signed_impact > 0 when OPPONENT's key player is out → score boost
15. NUCLEAR never fired live because max base = 85, need +5 situational. Injury boost covers this.
16. nba_api: _endpoint_factory injection pattern. Never unittest.mock.patch on nba_api classes.
17. "LA Clippers" edge case: nba_api returns "LA Clippers" not "Los Angeles Clippers"
18. Kill switch cache-seeding: write to _module_cache BEFORE calling pdo_kill_switch()
19. Edge test fixtures: tight prices (-108/-112) don't produce >3.5% edge — use outlier-book pattern
20. DFS FPTS ≠ raw PRA. KOTC uses raw P+R+A only (no 1.25x reb / 1.5x ast multipliers)
21. KOTC virtual profiles: Maxey-Embiid-out activates only when Embiid in injury_outs set

---

*This prompt was generated at end of Session 23. Next session is Session 24.*
*Current test count: 1007/1007. All commits pushed to GitHub main.*
