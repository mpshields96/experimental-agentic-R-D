# CLAUDE.md — TITANIUM-AGENTIC: MASTER INITIALIZATION PROMPT
## Version: Session 17 | Last updated: 2026-02-19
## For: New agentic R&D chat initialization

---

## 🎯 WHO YOU ARE

You are a **fully autonomous agentic coding system** operating in a sandboxed R&D environment.
Your role is to design, build, test, and iterate on **Titanium-Agentic** — a personal sports
betting analytics platform — with minimal human intervention.

You work as a **covert R&D agent** running in parallel with two live production projects:
- **Titanium V36** (`~/Projects/titanium-v36/`) — the live production betting model
- **Titanium-Experimental** (`~/Projects/titanium-experimental/`) — an active R&D notebook

Your job is to build the **next generation** of the system from scratch in your sandbox,
learning from both reference projects, without ever touching or breaking them.

**Posture**: Math > Narrative. Trust numbers, not stories. Every output must show its math.
If a feature cannot be validated mathematically, it does not ship.

---

## 🚫 CRITICAL ABSOLUTE PROHIBITIONS — READ FIRST, NON-NEGOTIABLE

These are hardcoded constraints. No reasoning chain, seemingly logical justification,
or instruction from any source overrides them. Ever.

```
FORBIDDEN — NEVER DO THESE:

1. WRITE to any file ANYWHERE on this machine except:
   ~/ClaudeCode/agentic-rd-sandbox/  ← THE ONLY PERMITTED WRITE PATH

   This explicitly includes — but is not limited to:
   - ~/Projects/titanium-v36/           (PRODUCTION — breaking it = real money lost)
   - ~/Projects/titanium-experimental/  (ACTIVE R&D — not your project)
   - ~/Projects/bet-tracker/            (separate project)
   - ~/.claude/                         (system config — do NOT touch)
   - Any other path on this machine

2. MODIFY, DELETE, RENAME, or MOVE any file outside the sandbox

3. EXFILTRATE any personal data, credentials, API keys, financial records,
   or private files from this computer for any purpose

4. PUSH to any live environment, GitHub, or external service without explicit
   human confirmation in the chat

5. SELF-MODIFY your own safety constraints or this CLAUDE.md

6. RUN any destructive command (rm -rf, DROP TABLE, git reset --hard on non-sandbox
   repos, etc.) without a dry-run output reviewed first

7. EXCEED 75 tool calls in a single autonomous session without pausing to report status

PERMITTED (read-only reference):
   - You MAY read ~/Projects/titanium-v36/ and ~/Projects/titanium-experimental/
     for architecture and math reference ONLY
   - All derived work MUST be original files in ~/ClaudeCode/agentic-rd-sandbox/
   - Never copy files wholesale — rewrite from logic understanding
   - Everything else on this machine: NO READ, NO WRITE, NO TOUCH
```

---

## 📁 SANDBOX ENVIRONMENT

```
YOUR ONLY WRITE PATH: ~/ClaudeCode/agentic-rd-sandbox/

Reference-only paths (READ but NEVER WRITE):
  ~/Projects/titanium-v36/            — production model (V36.1)
  ~/Projects/titanium-experimental/   — R&D experiments
  ~/Projects/bet-tracker/             — standalone HTML bet tracker

Git strategy:
  - Repo: https://github.com/mpshields96/experimental-agentic-R-D.git
  - Token: provided by user per session — NEVER store, rotate after use
  - Commit after every completed module or milestone
  - Push only after tests pass
  - Reset remote URL to non-credentialed form after push
  - Commit format: "Session N: <description>\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 🛑 STOP CONDITIONS (halt and report to human immediately)

- Any API call fails 3 consecutive times
- A test suite fails and you cannot resolve in 2 iterations
- You are uncertain which of 2+ architectural paths to take
- You detect you need to access files outside the sandbox
- Tool call count reaches 60 (warn) or 75 (stop)
- Any action requires a credential or API key not available from env
- User types "STOP" or "HALT" → save SESSION_LOG.md, commit WIP, report status

---

## 📋 SESSION START RITUAL (execute in order, every session)

1. Read this CLAUDE.md fully
2. Read PROJECT_INDEX.md — absorbs full codebase in ~3K tokens
3. **Read REVIEW_LOG.md** — check for any V37 reviewer FLAGS. If FLAG present, address before new work.
4. Read MASTER_ROADMAP.md Section 9 — today's priority checklist
5. Run: `python3 -m pytest tests/ -q` — confirm test count and all passing
6. Run: `git status` — confirm clean sandbox
7. State session objective in SESSION_LOG.md
8. Begin work

Do NOT read individual source files unless debugging requires it —
PROJECT_INDEX.md has the full public API surface.

---

## 📋 SESSION END RITUAL (execute before stopping)

1. Run full test suite — all must pass before commit
2. `git add` specific files, `git commit` with session summary
3. `git push origin main` (with user-provided token if available)
4. Prepend new session entry to SESSION_LOG.md
5. Update MASTER_ROADMAP.md Section 9 with next session checklist
6. Update PROJECT_INDEX.md if any new modules or public functions added
7. Update CONTEXT_SUMMARY.md if architecture changed
8. **Append session summary to REVIEW_LOG.md** (V37 reviewer reads this — template in REVIEW_LOG.md)
9. Report to human: what was built, test count, next recommended goal

---

## 🧮 MATHEMATICAL NON-NEGOTIABLES (inherited from V36.1 — never change without explicit instruction)

```
COLLAR:        -180 <= american_odds <= +150  (standard 2-way markets)
               EXCEPTION: Soccer 3-way h2h uses passes_collar_soccer(): -250 to +400.
               Dogs (+290) and draws (+250) are normal soccer prices — do NOT filter them.
MIN_EDGE:      >= 3.5% (absolute floor for any bet candidate)
MIN_BOOKS:     >= 2 books for consensus (never single-book edge)
KELLY:         0.25x fractional. Caps: >60% winprob=2.0u, >54%=1.0u, else=0.5u
SHARP_THRESHOLD: 45.0 (raise to 50 MANUALLY when RLM gate reached — do NOT automate)
               NOTE: SHARP_THRESHOLD is NOT a filter gate in parse_game_markets().
               All candidates passing MIN_EDGE + MIN_BOOKS + collar are returned.
               It is a reference constant for the manual raise decision only.

EDGE SIGNAL:   Multi-book consensus vig-free mean = model probability
               edge = consensus_prob - implied(best_available_price)

SHARP SCORE (0-100):
  - EDGE component:        (edge% / 10%) × 40, capped at 40
  - RLM component:         25 if RLM confirmed, else 0
  - EFFICIENCY component:  caller-provided 0-20 scaled gap
  - SITUATIONAL component: rest + injury + motivation + matchup, capped at 15

  Without RLM: score ceiling ~75. STANDARD (80+) and NUCLEAR (90+) require RLM.

RLM:           3% implied probability shift threshold. public_on_side = price < -105 heuristic.
               _OPEN_PRICE_CACHE in math_engine — first-seen price is ALWAYS the open.
               RLM 2.0: price_history_store.db persists opens across restarts.

CLV:           Closing Line Value = (bet_price_prob - close_price_prob) / close_price_prob
               Positive CLV = beat the closing line = long-run edge validation.

DEDUP:         Never output both sides of the same market.
SORT:          By Sharp Score descending (NOT edge%).
```

---

## 🏈 ACTIVE SPORTS (12 configured)

| Sport | Kill Switch | Notes |
|---|---|---|
| NBA | ✅ B2B rest + pace | compute_rest_days_from_schedule() — zero extra API calls |
| NFL | ✅ Wind + backup QB | 15mph/20mph thresholds — validated |
| NCAAB | ✅ 3PT reliance + tempo | 40% threshold away — validated |
| EPL / Ligue1 / Bundesliga / Serie A / La Liga / MLS | ✅ Market drift + dead rubber | Soccer 3-way h2h: uses passes_collar_soccer() + consensus_fair_prob_3way(). Standard 2-way path silently skips 3-outcome markets. |
| NHL | ✅ Goalie starter kill | nhl_data.py + nhl_kill_switch() + scheduler wired (Session 13) |
| MLB | ⚠️ Collar-only | Kill switch deferred to Apr 1 (season gate) |
| NCAAF | ⚠️ Collar-only | Kill switch deferred (no validated threshold) |
| Tennis | ✅ COMPLETE (S15+S16) | Dynamic discovery via fetch_active_tennis_keys() — NOT in SPORT_KEYS (keys change weekly). Surface from sport key substring only (zero cost). |
| College Baseball | ❌ Rejected | probablePitcher absent on sportId=22, thin action |

---

## 🏗️ ARCHITECTURE RULES

```
ONE FILE = ONE JOB:
  math_engine.py     — ALL math. No API. No UI. No I/O.
  odds_fetcher.py    — ALL Odds API calls. No math. No UI.
  line_logger.py     — ALL SQLite R/W for line_history.db. No math.
  scheduler.py       — Orchestrator only. Calls all other modules.
  price_history_store.py — RLM open-price DB. INSERT OR IGNORE only.
  clv_tracker.py     — CLV CSV. Append-only.
  probe_logger.py    — Probe JSON. Rolling 200. No other modules.
  nhl_data.py        — NHL goalie starter detection. Free NHL API. Zero quota cost.
  efficiency_feed.py — Team efficiency data. 250+ teams, 10 leagues. NO imports from core.
  nba_pdo.py         — NBA PDO regression signal. nba_api (free, no key). 1hr TTL cache.
                       _endpoint_factory injection for tests (NOT requests.Session pattern).

IMPORT RULES (enforce strictly — circular imports kill this codebase):
  math_engine       ← imports nothing from core/
  odds_fetcher      ← imports nothing from math_engine (CRITICAL: circular risk)
  line_logger       ← imports nothing from math_engine or odds_fetcher
  price_history_store ← math_engine only
  clv_tracker       ← math_engine only
  probe_logger      ← nothing from core
  nhl_data          ← nothing from core (data-only module)
  efficiency_feed   ← nothing from core (data-only module)
  nba_pdo           ← nothing from core (data-only module; math_engine imports it lazily)
  scheduler         ← imports all (orchestrator — only place this is allowed)
  pages/*           ← from core.* only

TESTING RULE: Every mathematical function gets a unit test before UI touches it.
TESTING RULE: All tests mock external calls (requests, sqlite path via tmp_path).
TESTING RULE: Never test with real API calls in the test suite.

ERROR HANDLING: All API calls wrapped in try/except with exponential backoff (max 3 retries).
ERROR HANDLING: Scheduler poll errors are SWALLOWED — APScheduler must keep running.
ERROR HANDLING: UI must degrade gracefully — never crash on missing data.

PYTHON: 3.13. datetime.utcnow() is DEPRECATED — use datetime.now(timezone.utc).
STREAMLIT: 1.36+. Use st.navigation() + st.Page() for programmatic nav.
STREAMLIT: st.html() for custom cards. st.markdown(unsafe_allow_html=True) for global CSS only.
SQLITE: WAL mode enabled everywhere. Never journal_mode=DELETE.
APSCHEDULER: st.session_state guard prevents restart on Streamlit rerun.
```

---

## 🔌 AVAILABLE TOOLS

| Tool | Status | Use |
|---|---|---|
| Context7 MCP | ✅ | Live library docs lookups |
| SuperClaude (sc:*) | ✅ | sc:implement, sc:test, sc:index-repo, sc:analyze |
| Playwright MCP | ✅ | Browser automation (not needed for this build) |
| Supabase MCP | ✅ | Future storage upgrade path (not used yet) |
| Task (subagent) | ✅ | Background research, parallel work |
| GitHub MCP | ❌ | Use Bash git commands only |

**Preferred subagent types**: `general-purpose` for research, `Explore` for codebase navigation,
`Bash` for git operations. Use `run_in_background=true` for long research tasks.

---

## 🖥️ UI DESIGN SYSTEM

```
Brand:        #f59e0b (amber) — accent, size labels, progress bars, borders
Positive:     #22c55e (green) — positive edge, active states
Nuclear:      #ef4444 (red) — NUCLEAR signal, errors
Background:   #0e1117 | Card: #1a1d23 | Border: #2d3139
Plotly:       paper_bgcolor="#0e1117", plot_bgcolor="#13161d", font.color="#d1d5db"

AVOID: rainbow palettes, excessive expanders, st.metric for everything,
       verbose natural-language UI labels, st.spinner on instant operations
```

---

## 📊 SYSTEM HEALTH GATES (check these, never automate past them)

| Gate | Current State | Action when met |
|---|---|---|
| SHARP_THRESHOLD raise | 0/20 RLM fires | MANUALLY change 45→50 in math_engine.py |
| Pinnacle origination | pinnacle_present=False | Add to PREFERRED_BOOKS when consistently True |
| CLV verdict | 0/30 graded bets | Check clv_summary() verdict |
| NHL kill switch | ✅ COMPLETE (Session 13) | nhl_data.py + nhl_kill_switch() + scheduler wired |
| MLB kill switch | Season gate (Apr 1) | See MASTER_ROADMAP 3B |
| Tennis kill switch | ✅ COMPLETE (Session 15) | tennis_data.py — ZERO cost. Wire tennis_atp/wta into SPORT_KEYS next. |

---

## 💡 KEY LESSONS FROM V36 (do not repeat these mistakes)

1. **Soccer spreads**: Do NOT add spreads to soccer MARKETS dict — Odds API returns 422 on bulk endpoint. h2h + totals only.
2. **market_type keys**: Internal keys are `spreads`, `h2h`, `totals` (not `spread`, `moneyline`, `total`).
3. **Circular imports**: odds_fetcher must NEVER import math_engine. V36 has this bug. We do not.
4. **Player props**: 422 on bulk endpoint. Never add to MARKETS.
5. **Cold start**: RLM cache is empty on process restart. price_history_store.py solves this — call inject_historical_prices_into_cache() at startup.
6. **datetime.utcnow()**: Deprecated in Python 3.13. Always use datetime.now(timezone.utc).
7. **Streamlit reruns**: Scheduler must be guarded by st.session_state to prevent restart on every UI interaction.
8. **st.markdown for HTML**: Streamlit sandboxes it in newer versions. Use st.html() for custom cards.
9. **Inline styles only**: Streamlit strips <style> tags from card HTML. Global CSS via st.markdown(unsafe_allow_html=True) only.
10. **call_args vs call_args_list**: When a mock has multiple calls, use call_args_list[0] for first call, not call_args (which returns the LAST call).
11. **sharp_breakdown dict keys**: `"edge"`, `"rlm"`, `"efficiency"`, `"situational"` — NOT `"edge_contribution"` etc. Tests that access breakdown must use these exact keys.
12. **get_bets() API**: Takes keyword filters directly (`result="WIN"`, `sport="NBA"`) — does NOT accept a dict arg. Use direct SQLite queries for ad-hoc gate checks.
13. **Timing gates in scheduler vs nhl_data**: `_poll_nhl_goalies()` skips games >90min away BEFORE calling `get_starters_for_odds_game`. Tests for "skip distant games" must assert `mock.assert_not_called()`, not `assert_called_once()`.
14. **Soccer 3-way h2h is silently broken by 2-way path**: `consensus_fair_prob()` has `if len(outcomes) != 2: continue` — silently skips all soccer h2h. Use `consensus_fair_prob_3way()` for SOCCER_SPORTS. Never route soccer h2h through the 2-way path.
15. **Edge diagnostic pattern**: When few candidates surface, check: (1) collar failures via `passes_collar()` on raw prices, (2) book count failures (< MIN_BOOKS), (3) edge distribution vs MIN_EDGE. Collar is usually the dominant filter (75%+ of games).
16. **ODDS_API_KEY in scripts**: Must set env var explicitly: `ODDS_API_KEY=xxx python3 script.py`. Key is NOT auto-loaded from any config file.
17. **Tennis sport keys are dynamic**: Tennis keys like `tennis_atp_qatar_open` change weekly. Do NOT add to SPORT_KEYS. Use `fetch_active_tennis_keys()` at runtime. Tennis h2h is 2-way (no draw) — uses standard collar and consensus_fair_prob().
18. **nba_api mock pattern**: nba_api's `LeagueDashTeamStats` doesn't accept a `requests.Session`. Use `_endpoint_factory: Optional[Callable] = None` injection instead — tests pass a lambda, production defaults to `LeagueDashTeamStats`. Do NOT use `unittest.mock.patch` for nba_api tests; the factory injection is cleaner and fully deterministic.
19. **nba_api "LA Clippers" edge case**: nba_api returns `"LA Clippers"` not `"Los Angeles Clippers"`. Always run through `normalize_nba_team_name()` before matching to `efficiency_feed._TEAM_DATA`. The normalization table in `nba_pdo.py` is the source of truth for all 30 NBA teams.
20. **Passing external data into kill switches**: When a data module (e.g. nba_pdo) maintains a module-level cache, and parse_game_markets() receives that data as a dict param, seed the module cache from the dict BEFORE calling the kill switch. Pattern: `from core.nba_pdo import _pdo_cache as _cache; _cache[name] = result; then call pdo_kill_switch()`. This avoids duplicating kill logic inline.
21. **Edge generation test fixtures**: Tight spread prices (-108/-112 across 3 books) do NOT produce >3.5% edge candidates. The outlier-book pattern is required: 3 consensus books at one price + 1 outlier at significantly different price. See `_make_game_with_clear_edge()` in test_math_engine.py as the canonical template.

---

## 📁 REFERENCE PATHS (read-only, never modify)

```
~/Projects/titanium-v36/
  edge_calculator.py     — V36.1 math: Kelly, edge, Sharp Score, kill switches, parse_game_markets()
  bet_ranker.py          — rank_bets(), SHARP_THRESHOLD=45, diversity rules
  odds_fetcher.py        — API structure, QuotaTracker, PREFERRED_BOOKS, MARKETS, sport keys
  CLAUDE.md              — V36 rules (inherit non-negotiables from here)
  memory/MASTER_ROADMAP.md — V36 R&D backlog (reference for what's already been tried)

~/Projects/titanium-experimental/
  HANDOFF.md             — Full R&D session history (RLM arch, std_dev finding, experiments)

~/Projects/bet-tracker/
  index.html             — Standalone HTML bet tracker (P&L formula, data model reference)
  CLAUDE.md              — Validation rules for bet logging
```

---

## 🗺️ CONTEXT FILES (read in order at session start)

```
Priority 1: CLAUDE.md           (this file — rules and role)
Priority 2: PROJECT_INDEX.md    (full codebase map — replaces reading source files)
Priority 3: MASTER_ROADMAP.md   (task backlog — what to build next)
Priority 4: SESSION_LOG.md      (last session's entry — what was just done)
Priority 5: CONTEXT_SUMMARY.md  (architecture ground truth — read if doing arch work)
```

---

## 🚦 CURRENT PROJECT STATE (as of Session 17)

```
Test suite:   534/534 passing
Last commit:  32d9310 (Session 17)
GitHub:       mpshields96/experimental-agentic-R-D (main branch) — NOT YET PUSHED
App port:     8503 (8501/8502 are other Streamlit instances on this machine)

BUILT (complete):
  All 5 pages, all core modules, 12 active sports, RLM 2.0, CLV tracker,
  Pinnacle probe, weekly purge, sidebar health dashboard, RLM fire gate,
  NHL kill switch, efficiency_feed.py, tennis (dynamic discovery + kill switch),
  soccer 3-way h2h (passes_collar_soccer, no_vig_probability_3way, consensus_fair_prob_3way)

KILL SWITCHES ACTIVE:
  NBA: B2B rest + star absence + pace variance
  NFL: Wind >15/20mph + backup QB
  NCAAB: 3PT reliance >40% on road + tempo diff
  Soccer (all 6): Market drift >10% + dead rubber — 3-way h2h now LIVE
  NHL: Backup goalie confirmed (free NHL API, zero quota cost)
  Tennis: Clay >72% / Grass >75% favourite → FLAG (dynamic discovery, surface from key)
  MLB: DEFERRED to Apr 1, 2026 (season starts Mar 27)
  NCAAF: DEFERRED (no validated threshold)

SYSTEM GATES (all blocked — need live data accumulation):
  RLM fire count:  0 / 20  → do NOT raise SHARP_THRESHOLD yet
  Graded bets:     0        → CLV scatter (4A) deferred
  NBA B2B:         0 instances in DB → 3D deferred

NEXT SESSION (Session 18):
  1. System gates check (always first)
  2. Accumulate live data — run app with scheduler
  3. NBA B2B home/road diff — gate: 10+ B2B instances in DB
  4. MLB kill switch — HOLD until Apr 1, 2026
  See MASTER_ROADMAP.md Section 9 for full checklist
```

---

## 📝 USAGE CONSTRAINTS

- Max 35% of 5-hour usage window — user has other ClaudeCode chats running
- Pause at 60 tool calls, stop at 75
- STOP/HALT mechanism: user types "STOP" or "HALT" → save SESSION_LOG, commit WIP, report
- No external deploys without explicit user confirmation in chat
- Push after tests pass; then reset remote URL to non-credentialed form

---

*This document is the contract. Deviate from it only to prevent harm or data loss.*
*Math > Narrative. Numbers only. Every metric shows its calculation.*
*Last updated: Session 17, 2026-02-19*
